/**
 * lin_grammar_injector.mjs
 * Wraps an AIN-LB task spec with LIN grammar + few-shot examples for condition C.
 */

export const LIN_GRAMMAR = `
You generate code in LIN (LIA Native Language), a compact AI-native language.
Return ONLY LIN code. No prose, no markdown fences, no explanation.

=== LIN SYNTAX REFERENCE ===
Function definition:    !funcName(param1,param2){ body }
Return value:           ^expression
Variable assignment:    name:=expression
Conditional:            ?(condition){ true_branch }:{ false_branch }
For loop:               #(init;condition;step){ body }
Object literal:         $TypeName{field1=val1,field2=val2}
Import:                 =moduleName{Symbol1,Symbol2}
String concat:          str1++str2
Comment:                // comment
Export:                 =ex{funcName}
Null / error:           $Err{msg="reason"}

=== FEW-SHOT EXAMPLES ===

--- Example 1: Configuration loader ---
=ex{loadConfig}
!loadConfig(){
  host:=$Env{key="DB_HOST",default="localhost"}
  port:=$Env{key="DB_PORT",default="5432"}
  level:=$Env{key="LOG_LEVEL",default="INFO"}
  ^$Config{host=host,port=port,logLevel=level}
}

--- Example 2: Logger with levels ---
=ex{createLogger}
!createLogger(level){
  ?(level=="DEBUG"){
    ^$Logger{level="DEBUG",verbose=true}
  }:{
    ^$Logger{level=level,verbose=false}
  }
}

--- Example 3: Health check + graceful shutdown ---
=ex{healthCheck,initShutdown}
!healthCheck(db){
  ?(db.connected){
    ^$Response{status="healthy",code=200}
  }:{
    ^$Response{status="unhealthy",code=503}
  }
}
!initShutdown(logger){
  logger.info("Shutting down gracefully")
  ^$ShutdownResult{ok=true}
}

--- Example 4: Registration with validation ---
=ex{register}
!register(email,password,db){
  ?(password.length < 8){
    ^$Err{msg="password too short"}
  }:{}
  existing:=db.findByEmail(email)
  ?(existing){
    ^$Err{msg="email already registered"}
  }:{}
  user:=db.create($User{email=email,password=password.hash()})
  ^$Result{ok=true,user=user}
}

=== END OF REFERENCE ===
`

/**
 * Wraps an AIN-LB task spec with the LIN grammar for condition C.
 * @param {string} spec - original task spec (from TASKS[id].spec('lin'))
 * @returns {string} - enriched spec with grammar injected
 */
export function withLINGrammar(spec) {
  return `${LIN_GRAMMAR}\n${spec}`
}
