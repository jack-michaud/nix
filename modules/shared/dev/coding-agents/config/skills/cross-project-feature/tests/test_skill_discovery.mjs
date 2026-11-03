// Real installed loader; all synthetic discovery paths stay in task TMPDIR.
// A neutral link here is a fixture, NOT a change to managed Pi distribution.
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

assert(process.env.TMPDIR, 'Use task-owned TMPDIR');
assert(process.env.PI_PACKAGE_ROOT, 'Set installed pi-coding-agent package path');
const packageRoot = resolve(process.env.PI_PACKAGE_ROOT);
const source = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = await mkdtemp(join(process.env.TMPDIR, 'feature-loader-'));
const home = join(root, 'home');
const agentDir = join(home, '.pi', 'agent');
const cwd = join(root, 'project');
process.env.HOME = home;
process.env.PI_CODING_AGENT_DIR = agentDir;
process.env.XDG_CONFIG_HOME = join(home, '.config');
process.env.XDG_CACHE_HOME = join(home, '.cache');
const name = 'cross-project-feature';
const neutral = join(home, '.agents', 'skills');
const link = join(neutral, name);
try {
  await Promise.all([mkdir(neutral, { recursive: true }),
    mkdir(agentDir, { recursive: true }), mkdir(join(cwd, '.git'), { recursive: true })]);
  await symlink(source, link, 'dir');
  const { DefaultResourceLoader } = await import(pathToFileURL(
    join(packageRoot, 'dist/core/resource-loader.js')).href);
  const { formatSkillsForPrompt } = await import(pathToFileURL(
    join(packageRoot, 'dist/core/skills.js')).href);
  const load = async (noSkills = false) => {
    const loader = new DefaultResourceLoader({ cwd, agentDir, noSkills,
      noExtensions: true, noThemes: true, noPromptTemplates: true, noContextFiles: true });
    await loader.reload({ resolveProjectTrust: async () => false });
    assert.deepEqual(loader.getExtensions().errors, []);
    return loader.getSkills();
  };
  let result = await load();
  assert.equal(result.skills.length, 1);
  assert.deepEqual(result.diagnostics, []);
  assert.equal(result.skills[0].name, name);
  assert.equal(await realpath(result.skills[0].filePath), join(await realpath(source), 'SKILL.md'));
  assert(formatSkillsForPrompt(result.skills).includes('<name>' + name + '</name>'));
  assert(formatSkillsForPrompt(result.skills).includes('owner-authorized'));
  assert(!result.skills[0].disableModelInvocation);
  await symlink(source, join(neutral, 'alias'), 'dir');
  assert.equal((await load()).skills.length, 1, 'deduplicate by realpath');
  await writeFile(join(agentDir, 'settings.json'), JSON.stringify({ skills: ['-' + link, '-' + join(neutral, 'alias')] }));
  assert.equal((await load()).skills.length, 0, 'respect explicit exclusion');
  await writeFile(join(agentDir, 'settings.json'), '{}');
  assert.equal((await load(true)).skills.length, 0, 'respect noSkills');
  console.log(JSON.stringify({ passed: true, activation: false, globalInstall: false }));
} finally {
  await rm(root, { recursive: true, force: true });
}
