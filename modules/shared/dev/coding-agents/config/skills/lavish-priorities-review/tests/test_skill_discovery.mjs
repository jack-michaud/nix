// Uses the real installed resource loader, not a frontmatter-only approximation.
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

assert(process.env.TMPDIR, 'Use your task-owned TMPDIR');
assert(process.env.PI_PACKAGE_ROOT, 'Set PI_PACKAGE_ROOT to the installed pi-coding-agent package');
const packageRoot = resolve(process.env.PI_PACKAGE_ROOT);
const source = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = await mkdtemp(join(process.env.TMPDIR, 'review-loader-'));
const home = join(root, 'home');
const agentDir = join(home, '.pi', 'agent');
const cwd = join(root, 'project');
// Establish isolation before importing Pi: it caches some environment paths.
process.env.HOME = home;
process.env.PI_CODING_AGENT_DIR = agentDir;
process.env.XDG_CONFIG_HOME = join(home, '.config');
process.env.XDG_CACHE_HOME = join(home, '.cache');
const neutralDir = join(home, '.agents', 'skills');
const name = 'lavish-priorities-review';
const link = join(neutralDir, name);
const importFile = (path) => import(pathToFileURL(join(packageRoot, path)).href);

try {
  await Promise.all([mkdir(neutralDir, { recursive: true }), mkdir(agentDir, { recursive: true }),
    mkdir(join(cwd, '.git'), { recursive: true })]);
  await symlink(source, link, 'dir');
  const { DefaultResourceLoader } = await importFile('dist/core/resource-loader.js');
  const { formatSkillsForPrompt } = await importFile('dist/core/skills.js');
  const version = JSON.parse(await readFile(join(packageRoot, 'package.json'), 'utf8')).version;
  const load = async ({ trusted = false, noSkills = false } = {}) => {
    const loader = new DefaultResourceLoader({ cwd, agentDir, noSkills,
      noExtensions: true, noThemes: true, noPromptTemplates: true, noContextFiles: true });
    await loader.reload({ resolveProjectTrust: async () => trusted });
    assert.deepEqual(loader.getExtensions().errors, []);
    return loader.getSkills();
  };
  let result = await load();
  assert.equal(result.skills.length, 1, 'native neutral automatic discovery');
  assert.equal(result.skills[0].name, name);
  assert.equal(await realpath(result.skills[0].filePath), join(await realpath(source), 'SKILL.md'));
  assert.deepEqual(result.diagnostics, []);
  const prompt = formatSkillsForPrompt(result.skills);
  assert(prompt.includes(`<name>${name}</name>`));
  assert(prompt.includes('Review work-board priorities asynchronously'));
  assert(prompt.includes('<location>'));
  assert(!result.skills[0].disableModelInvocation);

  await symlink(source, join(neutralDir, 'same-real-file'), 'dir');
  result = await load();
  assert.equal(result.skills.length, 1, 'symlink aliases deduplicated by realpath');
  assert.deepEqual(result.diagnostics, []);
  await rm(join(neutralDir, 'same-real-file'));

  await writeFile(join(agentDir, 'settings.json'), JSON.stringify({ skills: [`-${link}`] }));
  result = await load();
  assert.equal(result.skills.length, 0, 'exact resource exclusion respected');
  await writeFile(join(agentDir, 'settings.json'), '{}');
  result = await load({ noSkills: true });
  assert.equal(result.skills.length, 0, 'loader noSkills respected');

  const collision = join(cwd, '.agents', 'skills', name);
  await mkdir(collision, { recursive: true });
  await writeFile(join(collision, 'SKILL.md'), `---\nname: ${name}\ndescription: Generic isolated project collision.\n---\n# Test\n`);
  result = await load();
  assert.equal(result.skills.length, 1, 'untrusted project skipped, neutral skill remains');
  assert(!result.skills[0].filePath.startsWith(cwd));
  result = await load({ trusted: true });
  assert.equal(result.skills.length, 1);
  assert.equal(result.skills[0].filePath, join(collision, 'SKILL.md'), 'project first wins at this version');
  assert(result.diagnostics.some(d => d.type === 'collision' && d.message.includes(name)));
  await rm(join(cwd, '.agents'), { recursive: true });

  const invalid = join(neutralDir, 'invalid');
  await mkdir(invalid);
  await writeFile(join(invalid, 'SKILL.md'), '---\nname: [broken\n---\n# Invalid\n');
  result = await load();
  assert.equal(result.skills.length, 1);
  assert(result.diagnostics.some(d => d.path === join(invalid, 'SKILL.md') && d.type === 'warning'));
  await writeFile(join(invalid, 'SKILL.md'), '---\nname: invalid\n---\n# Missing description\n');
  result = await load();
  assert.equal(result.skills.length, 1);
  assert(result.diagnostics.some(d => d.message.includes('description')));
  console.log(JSON.stringify({ passed: true, installedPiVersion: version,
    checked: ['native neutral symlink discovery', 'prompt metadata exposure', 'realpath dedup',
      'exclusion', 'noSkills', 'project trust', 'collision precedence', 'malformed YAML', 'missing description'],
    activation: false }));
} finally {
  await rm(root, { recursive: true, force: true });
}
