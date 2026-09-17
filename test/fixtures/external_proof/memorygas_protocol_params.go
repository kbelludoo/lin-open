	QuadCoeffDiv          uint64 = 512   // Divisor for the quadratic particle of the memory cost equation.
	MemoryGas             uint64 = 3     // Times the address of the (highest referenced byte in memory + 1). NOTE: referencing happens on read, write and in instructions such as RETURN and CALL.
