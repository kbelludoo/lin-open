pub(crate) fn compute_feerate_sat_per_1000_weight(fee_sat: u64, weight: u64) -> u32 {
	(fee_sat * 1000 / weight).try_into().unwrap_or(u32::max_value())
}
pub(crate) const fn fee_for_weight(feerate_sat_per_1000_weight: u32, weight: u64) -> u64 {
	((feerate_sat_per_1000_weight as u64 * weight) + 1000 - 1) / 1000
}
