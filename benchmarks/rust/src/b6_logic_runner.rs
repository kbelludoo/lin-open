// B6_LOGIC_V1: Deductive Agent Capability & Policy Inference (Rust Engine)
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::time::Instant;

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
struct Binding {
    origin: String,
    target: String,
    cap: String,
}

#[derive(Default, Debug)]
struct LogicDiagnostics {
    nodes_explored: usize,
    backtracks: usize,
    unifications_attempted: usize,
    unifications_succeeded: usize,
}

struct KnowledgeBase {
    caps: HashSet<(String, String)>,
    active_contracts: HashSet<String>,
    trust_edges: Vec<(String, String, i32)>,
}

impl KnowledgeBase {
    fn load_b6_v1() -> Self {
        let mut caps = HashSet::new();
        for (ag, c) in &[
            ("ag_01", "cap_read"), ("ag_01", "cap_write"), ("ag_01", "cap_delegate"),
            ("ag_02", "cap_read"), ("ag_02", "cap_transform"),
            ("ag_03", "cap_audit"),
            ("ag_04", "cap_read"), ("ag_04", "cap_delegate"),
            ("ag_05", "cap_transform"),
            ("ag_06", "cap_write"),
            ("ag_07", "cap_audit"),
            ("ag_08", "cap_read"),
            ("ag_09", "cap_transform"),
            ("ag_10", "cap_delegate"),
        ] {
            caps.insert((ag.to_string(), c.to_string()));
        }

        let mut active_contracts = HashSet::new();
        for ag in &["ag_01", "ag_02", "ag_04", "ag_05", "ag_06", "ag_08", "ag_09", "ag_10"] {
            active_contracts.insert(ag.to_string());
        }

        let trust_edges = vec![
            ("ag_01".to_string(), "ag_02".to_string(), 4),
            ("ag_01".to_string(), "ag_04".to_string(), 5),
            ("ag_02".to_string(), "ag_05".to_string(), 3),
            ("ag_04".to_string(), "ag_08".to_string(), 4),
            ("ag_04".to_string(), "ag_09".to_string(), 2),
            ("ag_06".to_string(), "ag_01".to_string(), 5),
            ("ag_06".to_string(), "ag_07".to_string(), 3),
            ("ag_07".to_string(), "ag_03".to_string(), 4),
            ("ag_10".to_string(), "ag_06".to_string(), 4),
        ];

        Self { caps, active_contracts, trust_edges }
    }

    // Direct delegation check with unification & backtracking telemetry
    fn direct_delegates(&self, diag: &mut LogicDiagnostics) -> Vec<Binding> {
        let mut results = Vec::new();
        let all_capabilities = ["cap_read", "cap_write", "cap_audit", "cap_delegate", "cap_transform"];

        for (from, to, level) in &self.trust_edges {
            diag.nodes_explored += 1;
            diag.unifications_attempted += 1;

            if *level >= 3 {
                diag.unifications_succeeded += 1;
                diag.unifications_attempted += 1;

                if self.active_contracts.contains(to) {
                    diag.unifications_succeeded += 1;
                    diag.unifications_attempted += 1;

                    if self.caps.contains(&(from.clone(), "cap_delegate".to_string())) {
                        diag.unifications_succeeded += 1;

                        for cap in &all_capabilities {
                            diag.unifications_attempted += 1;
                            if self.caps.contains(&(from.clone(), cap.to_string())) {
                                diag.unifications_succeeded += 1;
                                results.push(Binding {
                                    origin: from.clone(),
                                    target: to.clone(),
                                    cap: cap.to_string(),
                                });
                            } else {
                                diag.backtracks += 1;
                            }
                        }
                    } else {
                        diag.backtracks += 1;
                    }
                } else {
                    diag.backtracks += 1;
                }
            } else {
                diag.backtracks += 1;
            }
        }
        results
    }

    // SLD Chain Resolution (Base + Recursive Step)
    fn resolve_chain(&self, diag: &mut LogicDiagnostics) -> (Vec<Binding>, Vec<Binding>) {
        let direct = self.direct_delegates(diag);
        let mut raw_derivations = direct.clone();

        // Recursive chain expansion
        let mut frontier: Vec<(String, String, String, usize)> = direct
            .iter()
            .filter(|b| b.cap == "cap_delegate")
            .map(|b| (b.origin.clone(), b.target.clone(), b.cap.clone(), 1))
            .collect();

        while let Some((orig, intermediate, _, depth)) = frontier.pop() {
            if depth > 10 { continue; } // Cycle protection
            diag.nodes_explored += 1;

            for next in &direct {
                diag.unifications_attempted += 1;
                if next.origin == intermediate {
                    diag.unifications_succeeded += 1;
                    raw_derivations.push(Binding {
                        origin: orig.clone(),
                        target: next.target.clone(),
                        cap: next.cap.clone(),
                    });

                    if next.cap == "cap_delegate" {
                        frontier.push((orig.clone(), next.target.clone(), next.cap.clone(), depth + 1));
                    }
                } else {
                    diag.backtracks += 1;
                }
            }
        }

        let mut distinct_set = BTreeSet::new();
        for d in &raw_derivations {
            distinct_set.insert(d.clone());
        }

        let distinct_list: Vec<Binding> = distinct_set.into_iter().collect();
        (raw_derivations, distinct_list)
    }
}

fn main() {
    let kb = KnowledgeBase::load_b6_v1();
    let mut diag = LogicDiagnostics::default();

    let start = Instant::now();
    let (raw_derivations, distinct_solutions) = kb.resolve_chain(&mut diag);
    let wall_time_us = start.elapsed().as_micros();

    let total_count = raw_derivations.len();
    let distinct_count = distinct_solutions.len();
    let eliminated = total_count - distinct_count;

    // Serialize bindings to canonical JSON
    let mut bindings_json = String::from("[");
    for (i, b) in distinct_solutions.iter().enumerate() {
        if i > 0 { bindings_json.push(','); }
        bindings_json.push_str(&format!("{{\"?Cap\":\"{}\",\"?Origin\":\"{}\",\"?Target\":\"{}\"}}", b.cap, b.origin, b.target));
    }
    bindings_json.push(']');

    println!("{{\"engine\":\"rust-native\",\"version\":\"1.97.1\",\"spec_id\":\"B6_LOGIC_V1\",\"status\":\"SUCCESS\",\"solutions_distinct\":{},\"solutions_total_derivations\":{},\"duplicate_bindings_eliminated\":{},\"diagnostics\":{{\"nodes_explored\":{},\"backtracks\":{},\"unifications_attempted\":{},\"unifications_succeeded\":{},\"wall_time_us\":{}}},\"bindings\":{}}}",
        distinct_count, total_count, eliminated,
        diag.nodes_explored, diag.backtracks, diag.unifications_attempted, diag.unifications_succeeded,
        wall_time_us, bindings_json);
}
