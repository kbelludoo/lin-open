(* B6_LOGIC_V1: Deductive Agent Capability & Policy Inference (OCaml Functional Engine) *)

type agent = string
type capability = string
type domain = string

type binding = {
  origin: agent;
  target: agent;
  cap: capability;
}

module BindingOrder = struct
  type t = binding
  let compare a b =
    let c1 = String.compare a.origin b.origin in
    if c1 <> 0 then c1
    else
      let c2 = String.compare a.target b.target in
      if c2 <> 0 then c2
      else String.compare a.cap b.cap
end

module BindingSet = Set.Make(BindingOrder)

type diag = {
  mutable nodes_explored: int;
  mutable backtracks: int;
  mutable unifications_attempted: int;
  mutable unifications_succeeded: int;
}

let caps_kb = [
  ("ag_01", "cap_read"); ("ag_01", "cap_write"); ("ag_01", "cap_delegate");
  ("ag_02", "cap_read"); ("ag_02", "cap_transform");
  ("ag_03", "cap_audit");
  ("ag_04", "cap_read"); ("ag_04", "cap_delegate");
  ("ag_05", "cap_transform");
  ("ag_06", "cap_write");
  ("ag_07", "cap_audit");
  ("ag_08", "cap_read");
  ("ag_09", "cap_transform");
  ("ag_10", "cap_delegate");
]

let active_contracts_kb = [
  "ag_01"; "ag_02"; "ag_04"; "ag_05"; "ag_06"; "ag_08"; "ag_09"; "ag_10"
]

let trust_edges_kb = [
  ("ag_01", "ag_02", 4);
  ("ag_01", "ag_04", 5);
  ("ag_02", "ag_05", 3);
  ("ag_04", "ag_08", 4);
  ("ag_04", "ag_09", 2);
  ("ag_06", "ag_01", 5);
  ("ag_06", "ag_07", 3);
  ("ag_07", "ag_03", 4);
  ("ag_10", "ag_06", 4);
]

let all_capabilities = [
  "cap_read"; "cap_write"; "cap_audit"; "cap_delegate"; "cap_transform"
]

let has_cap ag cap =
  List.exists (fun (a, c) -> a = ag && c = cap) caps_kb

let is_active ag =
  List.mem ag active_contracts_kb

let resolve_direct diag =
  List.fold_left (fun acc (from_ag, to_ag, level) ->
    diag.nodes_explored <- diag.nodes_explored + 1;
    diag.unifications_attempted <- diag.unifications_attempted + 1;
    if level >= 3 then begin
      diag.unifications_succeeded <- diag.unifications_succeeded + 1;
      diag.unifications_attempted <- diag.unifications_attempted + 1;
      if is_active to_ag then begin
        diag.unifications_succeeded <- diag.unifications_succeeded + 1;
        diag.unifications_attempted <- diag.unifications_attempted + 1;
        if has_cap from_ag "cap_delegate" then begin
          diag.unifications_succeeded <- diag.unifications_succeeded + 1;
          List.fold_left (fun inner_acc cap ->
            diag.unifications_attempted <- diag.unifications_attempted + 1;
            if has_cap from_ag cap then begin
              diag.unifications_succeeded <- diag.unifications_succeeded + 1;
              { origin = from_ag; target = to_ag; cap } :: inner_acc
            end else begin
              diag.backtracks <- diag.backtracks + 1;
              inner_acc
            end
          ) acc all_capabilities
        end else begin
          diag.backtracks <- diag.backtracks + 1;
          acc
        end
      end else begin
        diag.backtracks <- diag.backtracks + 1;
        acc
      end
    end else begin
      diag.backtracks <- diag.backtracks + 1;
      acc
    end
  ) [] trust_edges_kb

let rec expand_frontier direct frontier acc diag depth =
  if depth > 10 then acc
  else match frontier with
  | [] -> acc
  | (orig, interm, _) :: rest ->
      diag.nodes_explored <- diag.nodes_explored + 1;
      let new_derivs, new_frontier =
        List.fold_left (fun (d_acc, f_acc) next ->
          diag.unifications_attempted <- diag.unifications_attempted + 1;
          if next.origin = interm then begin
            diag.unifications_succeeded <- diag.unifications_succeeded + 1;
            let b = { origin = orig; target = next.target; cap = next.cap } in
            let f = if next.cap = "cap_delegate" then (orig, next.target, next.cap) :: f_acc else f_acc in
            (b :: d_acc, f)
          end else begin
            diag.backtracks <- diag.backtracks + 1;
            (d_acc, f_acc)
          end
        ) ([], []) direct
      in
      expand_frontier direct (new_frontier @ rest) (new_derivs @ acc) diag (depth + 1)

let resolve_all diag =
  let direct = resolve_direct diag in
  let delegating = List.filter (fun b -> b.cap = "cap_delegate") direct in
  let initial_frontier = List.map (fun b -> (b.origin, b.target, b.cap)) delegating in
  let chained = expand_frontier direct initial_frontier [] diag 1 in
  let all_derivations = direct @ chained in
  let distinct_set = List.fold_left (fun set b -> BindingSet.add b set) BindingSet.empty all_derivations in
  let distinct_list = BindingSet.elements distinct_set in
  (all_derivations, distinct_list)

let () =
  let diag = { nodes_explored = 0; backtracks = 0; unifications_attempted = 0; unifications_succeeded = 0 } in
  let t0 = Sys.time () in
  let (raw_derivs, distinct_list) = resolve_all diag in
  let t1 = Sys.time () in
  let wall_time_us = int_of_float ((t1 -. t0) *. 1_000_000.0) in
  let total_count = List.length raw_derivs in
  let distinct_count = List.length distinct_list in
  let eliminated = total_count - distinct_count in

  let bindings_json =
    "[" ^ (String.concat "," (List.map (fun b ->
      Printf.sprintf "{\"\\?Cap\":\"%s\",\"\\?Origin\":\"%s\",\"\\?Target\":\"%s\"}" b.cap b.origin b.target
    ) distinct_list)) ^ "]"
  in

  Printf.printf "{\"engine\":\"ocaml-functional\",\"version\":\"2.1.6\",\"spec_id\":\"B6_LOGIC_V1\",\"status\":\"SUCCESS\",\"solutions_distinct\":%d,\"solutions_total_derivations\":%d,\"duplicate_bindings_eliminated\":%d,\"diagnostics\":{\"nodes_explored\":%d,\"backtracks\":%d,\"unifications_attempted\":%d,\"unifications_succeeded\":%d,\"wall_time_us\":%d},\"bindings\":%s}\n"
    distinct_count total_count eliminated
    diag.nodes_explored diag.backtracks diag.unifications_attempted diag.unifications_succeeded
    wall_time_us bindings_json
