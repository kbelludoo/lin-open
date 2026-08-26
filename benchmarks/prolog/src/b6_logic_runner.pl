% B6_LOGIC_V1: Deductive Agent Capability & Policy Inference (Prolog Runner)
:- use_module(library(http/json)).

% Knowledge Base: Facts
has_capability(ag_01, cap_read).
has_capability(ag_01, cap_write).
has_capability(ag_01, cap_delegate).
has_capability(ag_02, cap_read).
has_capability(ag_02, cap_transform).
has_capability(ag_03, cap_audit).
has_capability(ag_04, cap_read).
has_capability(ag_04, cap_delegate).
has_capability(ag_05, cap_transform).
has_capability(ag_06, cap_write).
has_capability(ag_07, cap_audit).
has_capability(ag_08, cap_read).
has_capability(ag_09, cap_transform).
has_capability(ag_10, cap_delegate).

in_domain(ag_01, dom_nucleus).
in_domain(ag_02, dom_gateway).
in_domain(ag_03, dom_isolated).
in_domain(ag_04, dom_gateway).
in_domain(ag_05, dom_sandbox).
in_domain(ag_06, dom_nucleus).
in_domain(ag_07, dom_isolated).
in_domain(ag_08, dom_sandbox).
in_domain(ag_09, dom_gateway).
in_domain(ag_10, dom_nucleus).

contract_active(ag_01).
contract_active(ag_02).
contract_active(ag_04).
contract_active(ag_05).
contract_active(ag_06).
contract_active(ag_08).
contract_active(ag_09).
contract_active(ag_10).

trust_edge(ag_01, ag_02, 4).
trust_edge(ag_01, ag_04, 5).
trust_edge(ag_02, ag_05, 3).
trust_edge(ag_04, ag_08, 4).
trust_edge(ag_04, ag_09, 2).
trust_edge(ag_06, ag_01, 5).
trust_edge(ag_06, ag_07, 3).
trust_edge(ag_07, ag_03, 4).
trust_edge(ag_10, ag_06, 4).

% Rules
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

% Main Entry
main :-
    statistics(runtime, [T0, _]),
    statistics(inferences, Inf0),
    
    % Find all derivations
    findall(sol(Origin, Target, Cap), chain_delegate(Origin, Target, Cap), RawDerivations),
    
    statistics(inferences, Inf1),
    statistics(runtime, [T1, _]),
    
    length(RawDerivations, TotalDerivations),
    sort(RawDerivations, DistinctList),
    length(DistinctList, DistinctCount),
    Eliminated is TotalDerivations - DistinctCount,
    
    WallTimeUs is (T1 - T0) * 1000,
    InferencesCount is Inf1 - Inf0,
    
    format_bindings(DistinctList, BindingsJson),
    
    format('{"engine":"swi-prolog","version":"10.0.2","spec_id":"B6_LOGIC_V1","status":"SUCCESS","solutions_distinct":~w,"solutions_total_derivations":~w,"duplicate_bindings_eliminated":~w,"diagnostics":{"inferences_count":~w,"wall_time_us":~w},"bindings":~w}~n',
           [DistinctCount, TotalDerivations, Eliminated, InferencesCount, WallTimeUs, BindingsJson]),
    halt(0).

format_bindings([], '[]').
format_bindings([sol(O, T, C)|Rest], JsonStr) :-
    format_bindings_loop([sol(O, T, C)|Rest], Items),
    atomic_list_concat(Items, ',', Joined),
    atom_concat('[', Joined, Temp),
    atom_concat(Temp, ']', JsonStr).

format_bindings_loop([], []).
format_bindings_loop([sol(O, T, C)|Rest], [Item|RestItems]) :-
    format(atom(Item), '{"?Cap":"~w","?Origin":"~w","?Target":"~w"}', [C, O, T]),
    format_bindings_loop(Rest, RestItems).

:- initialization(main, main).
