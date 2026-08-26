// Helper script to inspect oracle assertions matching in B9
import fs from 'node:fs';
const spec = JSON.parse(fs.readFileSync('spec/B9_AGENT_REAL_SPEC_V1.json', 'utf8'));
for (const ep of spec.scenarios_spec.episodes) {
  console.log(`${ep.episode_id}:`, JSON.stringify(ep.task_oracle.required_state_assertions));
}
