% B6_LOGIC_V2: Deductive Inference, Scalability, Cycle-Safety & Proof DAG (SWI-Prolog Engine)
:- use_module(library(http/json)).
:- use_module(library(lists)).
:- use_module(library(apply)).
:- use_module(library(tables)).

:- dynamic has_capability/2.
:- dynamic in_domain/2.
:- dynamic contract_active/1.
:- dynamic trust_edge/3.
:- dynamic direct_delegate/3.

:- table chain_delegate/3.

direct_delegate(A, B, Cap) :-
    has_capability(A, cap_delegate),
    has_capability(A, Cap),
    trust_edge(A, B, Level),
    Level >= 3,
    contract_active(B).

chain_delegate(A, B, Cap) :-
    direct_delegate(A, B, Cap).
chain_delegate(A, C, Cap) :-
    direct_delegate(A, B, cap_delegate),
    chain_delegate(B, C, Cap).

load_spec(SpecPath) :-
    open(SpecPath, read, Stream),
    json_read_dict(Stream, Dict),
    close(Stream),
    KB = Dict.knowledge_base,
    
    forall(member(F, KB.facts),
           ( Rel = F.rel,
             Args = F.args,
             ( Rel == "has_capability" -> [A, C] = Args, atom_string(AgAtom, A), atom_string(CapAtom, C), assertz(has_capability(AgAtom, CapAtom))
             ; Rel == "contract_active" -> [A] = Args, atom_string(AgAtom, A), assertz(contract_active(AgAtom))
             ; Rel == "in_domain" -> [A, D] = Args, atom_string(AgAtom, A), atom_string(DomAtom, D), assertz(in_domain(AgAtom, DomAtom))
             ; Rel == "trust_edge" -> [A, B, L] = Args, atom_string(AAtom, A), atom_string(BAtom, B), assertz(trust_edge(AAtom, BAtom, L))
             ; true
             )
           )).

% Q1: Existence
run_q1(Q1Json) :-
    (   chain_delegate(ag_001, ag_003, cap_read)
    ->  Q1Json = '{"first_binding":{"?Cap":"cap_read","?Origin":"ag_001","?Target":"ag_003"},"has_solution":true,"query_id":"Q1","status":"SUCCESS","type":"existence"}'
    ;   Q1Json = '{"first_binding":null,"has_solution":false,"query_id":"Q1","status":"FAILURE","type":"existence"}'
    ).

% Q2: Enumerate
run_q2(Q2Json) :-
    findall(sol(Target, Cap), chain_delegate(ag_001, Target, Cap), RawList),
    sort(RawList, Sorted),
    length(Sorted, Count),
    maplist(format_q2_binding, Sorted, BindingStrings),
    atomic_list_concat(BindingStrings, ',', Joined),
    format(atom(Q2Json), '{"bindings":[~w],"distinct_solutions_count":~w,"query_id":"Q2","status":"SUCCESS","type":"enumerate"}', [Joined, Count]).

format_q2_binding(sol(T, C), Str) :-
    format(atom(Str), '{"?Cap":"~w","?Origin":"ag_001","?Target":"~w"}', [C, T]).

% Q3: Constrained
run_q3(Q3Json) :-
    Agents = [ag_001, ag_002, ag_003, ag_004, ag_005, ag_006, ag_007, ag_008, ag_009, ag_010],
    findall(sol3(Orig, Target, cap_write),
            ( member(Orig, Agents),
              chain_delegate(Orig, Target, cap_write),
              in_domain(Target, dom_core_03)
            ),
            RawList),
    sort(RawList, Sorted),
    length(Sorted, Count),
    maplist(format_q3_binding, Sorted, BindingStrings),
    atomic_list_concat(BindingStrings, ',', Joined),
    format(atom(Q3Json), '{"bindings":[~w],"distinct_solutions_count":~w,"query_id":"Q3","status":"SUCCESS","type":"constrained"}', [Joined, Count]).

format_q3_binding(sol3(O, T, C), Str) :-
    format(atom(Str), '{"?Cap":"~w","?Domain":"dom_core_03","?Origin":"~w","?Target":"~w"}', [C, O, T]).

% Q4: Proof DAG for chain_delegate(ag_001, ag_009, cap_write)
run_q4(Q4Json) :-
    (   find_proof_path(ag_001, ag_009, cap_write, Path)
    ->  format_proof_dag(Path, ProofDagJson),
        format(atom(Q4Json), '{"binding":{"?Cap":"cap_write","?Origin":"ag_001","?Target":"ag_009"},"proof_dag":~w,"query_id":"Q4","status":"SUCCESS","type":"proof_dag"}', [ProofDagJson])
    ;   Q4Json = '{"binding":null,"proof_dag":null,"query_id":"Q4","status":"FAILURE","type":"proof_dag"}'
    ).

find_proof_path(A, B, Cap, [step(A, B, Cap, Lvl, 0)]) :-
    trust_edge(A, B, Lvl),
    Lvl >= 3,
    contract_active(B),
    has_capability(A, cap_delegate),
    has_capability(A, Cap), !.
find_proof_path(A, C, Cap, [step(A, B, cap_delegate, Lvl, 0)|Rest]) :-
    trust_edge(A, B, Lvl),
    Lvl >= 3,
    contract_active(B),
    has_capability(A, cap_delegate),
    find_proof_path(B, C, Cap, Rest).

format_proof_dag(Path, JsonStr) :-
    length(Path, DerivLen),
    collect_nodes_and_edges(Path, 0, RawNodes, RawEdges),
    sort(RawNodes, SortedNodes),
    sort(RawEdges, SortedEdges),
    maplist(node_json, SortedNodes, NodeJsons),
    maplist(edge_json, SortedEdges, EdgeJsons),
    atomic_list_concat(NodeJsons, ',', NodesJoined),
    atomic_list_concat(EdgeJsons, ',', EdgesJoined),
    format(atom(JsonStr), '{"derivation_length":~w,"edges":[~w],"goal":{"?Cap":"cap_write","?Origin":"ag_001","?Target":"ag_009"},"nodes":[~w]}',
           [DerivLen, EdgesJoined, NodesJoined]).

collect_nodes_and_edges([], _, [], []).
collect_nodes_and_edges([step(From, To, Cap, Lvl, _)|Rest], StepIdx, [pnode(FactId, FactJson), pnode(GoalId, GoalJson)|RestNodes], [pedge(FactId, GoalId, EdgeJson)|RestEdges]) :-
    format(atom(FactId), 'fact:trust_edge(~w,~w,~w)', [From, To, Lvl]),
    format(atom(GoalId), 'goal:delegate(~w,~w,~w)', [From, To, Cap]),
    ( StepIdx == 0 -> Rule = 'R_DIRECT' ; Rule = 'R_CHAIN_REC' ),
    format(atom(FactJson), '{"args":["~w","~w",~w],"id":"~w","rel":"trust_edge","type":"fact"}', [From, To, Lvl, FactId]),
    format(atom(GoalJson), '{"args":["~w","~w","~w"],"id":"~w","rel":"delegate","type":"derived_goal"}', [From, To, Cap, GoalId]),
    format(atom(EdgeJson), '{"from":"~w","rule":"~w","to":"~w"}', [FactId, Rule, GoalId]),
    NextStep is StepIdx + 1,
    collect_nodes_and_edges(Rest, NextStep, RestNodes, RestEdges).

node_json(pnode(_, J), J).
edge_json(pedge(_, _, J), J).

% Q5: Negative Query
run_q5(Q5Json) :-
    (   chain_delegate(ag_100, ag_001, cap_revoke)
    ->  Q5Json = '{"bindings":[],"distinct_solutions_count":1,"finite_failure_proven":false,"query_id":"Q5","status":"SUCCESS","type":"negative_finite_failure"}'
    ;   Q5Json = '{"bindings":[],"distinct_solutions_count":0,"finite_failure_proven":true,"query_id":"Q5","status":"NO_SOLUTION","type":"negative_finite_failure"}'
    ).

% Q6: Deep Multi-Hop
run_q6(Q6Json) :-
    findall(sol6(Target, cap_transform), chain_delegate(ag_002, Target, cap_transform), RawList),
    sort(RawList, Sorted),
    length(Sorted, Count),
    maplist(format_q6_binding, Sorted, BindingStrings),
    atomic_list_concat(BindingStrings, ',', Joined),
    format(atom(Q6Json), '{"bindings":[~w],"distinct_solutions_count":~w,"query_id":"Q6","status":"SUCCESS","type":"deep_multi_hop"}', [Joined, Count]).

format_q6_binding(sol6(T, C), Str) :-
    format(atom(Str), '{"?Cap":"~w","?Origin":"ag_002","?Target":"~w"}', [C, T]).

main :-
    load_spec('spec/B6_LOGIC_SPEC_V2.json'),
    
    statistics(runtime, [T0, _]),
    statistics(inferences, Inf0),
    
    run_q1(Q1),
    run_q2(Q2),
    run_q3(Q3),
    run_q4(Q4),
    run_q5(Q5),
    run_q6(Q6),
    
    statistics(inferences, Inf1),
    statistics(runtime, [T1, _]),
    
    WallTimeUs is (T1 - T0) * 1000,
    TotalInferences is Inf1 - Inf0,
    
    format('{"engine":"swi-prolog","version":"10.0.2","spec_id":"B6_LOGIC_SPEC_V2","wall_time_us":~w,"diagnostics":{"inferences_count":~w},"queries":{"Q1":~w,"Q2":~w,"Q3":~w,"Q4":~w,"Q5":~w,"Q6":~w}}~n',
           [WallTimeUs, TotalInferences, Q1, Q2, Q3, Q4, Q5, Q6]),
    halt(0).

:- initialization(main, main).
