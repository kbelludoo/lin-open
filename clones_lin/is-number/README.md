@RULEL:CLONE_LIN:1.1.0
~R{.m=meta .c=compile .f=forbid .p=path}
.m{repo=clone-lin-is-number source="https://github.com/jonschlinkert/is-number.git" truth=LIN+RULEL_only intel="lia/INTEL_CLONE_LIN_is-number.rulel" nucleus=js!ts!py!go!rust!c!java}
.c{cmd="lin compile lin/<fn>.lin --target js|ts|py|go|rust|c|java -o out" restore="compile_back_to_original_behavior"}
.f{host_lang_in_repo .cjs .js .ts .py .go .rs compiled/}
.p{lin="lin/*.lin" readme=README.md fns="defaultExport" multi="js:P1/S0/F0 ts:P1/S0/F0 py:P1/S0/F0 go:P1/S0/F0 rust:P1/S0/F0 c:P1/S0/F0 java:P1/S0/F0" stub="EXPERIMENTAL_NOT_PASS cs,lua,elixir,crystal,kotlin,hcl,julia,scala,haskell,prolog,zig,nim,asm no_toolchain_no_oracle"}
