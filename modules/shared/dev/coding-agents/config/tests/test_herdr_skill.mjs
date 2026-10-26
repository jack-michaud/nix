// Run with node --test. Uses installed Pi exports, never creates an agent/model session.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { after, test } from 'node:test';

assert.ok(process.env.TMPDIR, 'TMPDIR must name your own temporary folder');
const scratch = mkdtempSync(join(process.env.TMPDIR, 'herdr-skill-'));
after(() => rmSync(scratch, { recursive: true, force: true }));
const source = resolve(dirname(fileURLToPath(import.meta.url)), '../skills/herdr-orchestration');
const piBinary = execFileSync('which', ['pi'], { encoding: 'utf8' }).trim();
const packageDir = process.env.PI_PACKAGE_DIR || resolve(dirname(realpathSync(piBinary)), '../..');
// Isolate all default discovery before importing Pi. No user settings/packages/auth read.
process.env.HOME = join(scratch, 'home');
process.env.PI_CODING_AGENT_DIR = join(process.env.HOME, '.pi/agent');
mkdirSync(process.env.HOME, { recursive: true });
const { loadSkills, formatSkillsForPrompt, DefaultResourceLoader, SettingsManager } =
  await import(pathToFileURL(join(packageDir, 'dist/index.js')).href);
const version = JSON.parse(readFileSync(join(packageDir, 'package.json'), 'utf8')).version;
console.log(`Installed Pi ${version}; package=${packageDir}; source=${source}`);

function setup(name) {
  const root = join(scratch, name);
  const cwd = join(root, 'project');
  const agentDir = join(root, '.pi/agent');
  mkdirSync(cwd, { recursive: true });
  mkdirSync(join(agentDir, 'skills'), { recursive: true });
  return { root, cwd, agentDir };
}
function load(f, paths = []) {
  return loadSkills({ cwd: f.cwd, agentDir: f.agentDir, skillPaths: paths, includeDefaults: true });
}
function fixtureSkill(path, content) {
  mkdirSync(path, { recursive: true });
  writeFileSync(join(path, 'SKILL.md'), content);
}

test('installed metadata parser and prompt discovery through native Pi symlink', async () => {
  const f = setup('native');
  const target = join(f.agentDir, 'skills/herdr-orchestration');
  symlinkSync(source, target, 'dir');
  const loader = new DefaultResourceLoader({
    cwd: f.cwd, agentDir: f.agentDir, settingsManager: SettingsManager.inMemory({ packages: [] }),
    noExtensions: true, noPromptTemplates: true, noThemes: true, noContextFiles: true,
  });
  await loader.reload();
  const result = loader.getSkills();
  assert.deepEqual(result.diagnostics, []);
  assert.equal(result.skills.length, 1);
  const skill = result.skills[0];
  assert.equal(skill.name, 'herdr-orchestration');
  assert.match(skill.description, /spoken orchestrator\/coordinator/);
  assert.match(skill.description, /Sesame/);
  assert.equal(skill.disableModelInvocation, false);
  assert.equal(realpathSync(skill.filePath), join(source, 'SKILL.md'));
  assert.ok(formatSkillsForPrompt(result.skills).includes('<name>herdr-orchestration</name>'));
  for (const relative of ['references/discovery.md', 'references/reporting.md', 'references/configuration.md']) {
    assert.ok(existsSync(join(skill.baseDir, relative)), relative);
  }
  console.log(JSON.stringify({ stage: 'isolated-discovery', installed: target,
    loaded: skill.filePath, resolved: realpathSync(skill.filePath), diagnostics: result.diagnostics }));
});

test('Prime alone is not Pi discovery; native Pi fan-out adds exactly one skill', () => {
  const f = setup('prime-only');
  const prime = join(f.root, '.prime/agent/skills');
  mkdirSync(prime, { recursive: true });
  symlinkSync(source, join(prime, 'herdr-orchestration'), 'dir');
  assert.equal(load(f).skills.length, 0);
  symlinkSync(source, join(f.agentDir, 'skills/herdr-orchestration'), 'dir');
  assert.equal(load(f).skills.length, 1);
  // Same resolved source through another path is deduplicated by the real loader.
  assert.equal(load(f, [source]).skills.length, 1);
  assert.deepEqual(load(f, [source]).diagnostics, []);
});

test('collisions warn and retain first identity; malformed metadata does not load', () => {
  const f = setup('negative');
  symlinkSync(source, join(f.agentDir, 'skills/herdr-orchestration'), 'dir');
  const duplicate = join(f.root, 'duplicate');
  fixtureSkill(duplicate, '---\nname: herdr-orchestration\ndescription: Duplicate fixture\n---\n');
  const invalid = join(f.root, 'invalid');
  fixtureSkill(invalid, '---\nname: invalid\n---\n');
  const malformed = join(f.root, 'malformed');
  fixtureSkill(malformed, '---\nname: [\n---\n');
  const result = load(f, [duplicate, invalid, malformed]);
  assert.equal(result.skills.length, 1);
  assert.equal(realpathSync(result.skills[0].filePath), join(source, 'SKILL.md'));
  assert.ok(result.diagnostics.some(d => d.type === 'collision'));
  assert.ok(result.diagnostics.some(d => d.message.includes('description')));
  assert.ok(result.diagnostics.some(d => d.path === join(malformed, 'SKILL.md')));
});

test('broken symlinks require explicit audit: Pi silently skips them', () => {
  const f = setup('broken');
  const link = join(f.agentDir, 'skills/herdr-orchestration');
  symlinkSync(join(f.root, 'does-not-exist'), link, 'dir');
  assert.equal(load(f).skills.length, 0);
  assert.throws(() => realpathSync(link), { code: 'ENOENT' });
  const explicit = load(f, [link]);
  assert.ok(explicit.diagnostics.some(d => d.message === 'skill path does not exist'));
});
