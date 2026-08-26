@RULEL:CLONE_LIN:1.1.0
~R{.m=meta .c=compile .f=forbid .p=path}
.m{repo=clone-lin-nanoid source="https://github.com/ai/nanoid.git" truth=LIN+RULEL_only intel="lia/INTEL_CLONE_LIN_nanoid.rulel" nucleus=ts!js!py!go!rust!c!java prefer_emit=ts}
.c{cmd="lin compile lin/<fn>.lin --target ts|js|py|go|rust|c|java -o out" restore="compile_back_to_original_behavior"}
.f{host_lang_in_repo .cjs .js .ts .py .go .rs compiled/}
.p{lin="lin/*.lin" readme=README.md fns="type_only!random!customRandom!customAlphabet!nanoid!fillRandom!random!customRandom!customAlphabet!nanoid!type_only!customAlphabet!nanoid!print!error" multi="ts:P13/S0/F0 js:P13/S0/F0 py:P13/S0/F0 go:P13/S0/F0 rust:P13/S0/F0 c:P13/S0/F0 java:P13/S0/F0" stub="EXPERIMENTAL_NOT_PASS cs,lua,elixir,crystal,kotlin,hcl,julia,scala,haskell,prolog,zig,nim,asm no_toolchain_no_oracle"}
