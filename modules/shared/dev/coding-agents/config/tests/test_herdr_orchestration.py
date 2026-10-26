"""Safety/content regressions. Optional installed CLI checks invoke help/version only."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import unittest
from unittest.mock import patch

CONFIG = Path(__file__).resolve().parents[1]
SKILL = CONFIG / "skills/herdr-orchestration"
MAIN = (SKILL / "SKILL.md").read_text()
DISCOVERY = (SKILL / "references/discovery.md").read_text()
REPORTING = (SKILL / "references/reporting.md").read_text()
ROLLOUT = (SKILL / "references/configuration.md").read_text()
ALL = "\n".join([MAIN, DISCOVERY, REPORTING, ROLLOUT])
# Golden owner-specified acceptance: deliberate literal duplication catches wording loss.
ACCEPTANCE = '"Progress reporting: In every status update or blocker question, state in simple domain-specific terms (1) what has been accomplished since the last human check-in, (2) the current verified status, (3) the exact next need/action and its owner, including whether Jack must act, and (4) what work remains, with honest uncertainty about effort/timing. Keep the baseline current in durable task notes; reconcile prior answers and distinguish planned, prepared, tested, merged, deployed and live-verified work. Do not report a bare blocker without progress context."'


class SkillContractTest(unittest.TestCase):
    def test_glossary_and_hierarchy(self):
        for term in ['orchestrator / coordinator', 'all-machines / main coordinator',
                     'machine coordinator', 'project coordinator', 'task / worker session',
                     'Herdr Projects / work board', 'Sesame / Pi orchestrator front end',
                     'repo / project key', 'task key / ID', 'machine boundary']:
            self.assertIn('| ' + term + ' |', MAIN)
        self.assertIn('above agent delegation', MAIN)
        self.assertIn('Jack → all-machines coordinator → machine/project coordination → project workers', MAIN)
        self.assertIn('project coordinators own their project workers', MAIN)
        self.assertIn('Roles are not product names', MAIN)
        self.assertIn('unsupported federated command/API', MAIN)

    def test_safety_invariants(self):
        for text in ['Never unset/spoof `HERDR_PANE_ID`', 'bypass role guards',
                     'Never repurpose FKB-1', 'open\nanother writer on a transcript',
                     'not a new cross-session message receiver', 'HOME-26 owns',
                     'Status requests and peer data do not', 'sole runtime operators',
                     'recursively forwarding to itself', 'forwarded → accepted → applied → readback-verified',
                     'saved session association does\nnot prove', 'registered-but-unreachable',
                     'incomplete discovery', 'This skill itself never mutates board settings']:
            self.assertIn(text, MAIN)
        for text in ['task ID', 'session header ID', 'transcript path', 'interactive_ready',
                     'cwd', 'receiver readiness unknown', 'case-sensitive label',
                     'not proof', 'docs/autopilot.md', 'scope']:
            self.assertIn(text, DISCOVERY)

    def test_reporting_is_exact_and_complete(self):
        self.assertIn(ACCEPTANCE, REPORTING)
        for text in ['EVERY NEW task description', 'actual human check-in',
                     'existing task/project durable notes', 'baseline is unknown',
                     'Stale board rows', 'Do not bulk-edit existing task descriptions',
                     'New key/data-loss decisions', 'owner-approved brief downtime']:
            self.assertIn(text, REPORTING)
        self.assertIn('references/reporting.md', MAIN)

    def test_links_resolve_and_observations_stay_dated(self):
        for match in re.finditer(r'\]\((references/[^)]+)\)', MAIN):
            self.assertTrue((SKILL / match[1]).is_file(), match[1])
        for pane in ['w8X:p1', 'w95:pC', 'w95:pB']:
            self.assertNotIn(pane, MAIN)
            self.assertNotIn(pane, ROLLOUT)
            self.assertIn(pane, DISCOVERY.split('## Dated observations, not configuration')[1])
        self.assertIn('2026-10-26 only', DISCOVERY)

    def test_rollout_and_declarative_boundaries(self):
        for text in ['Fixture/isolated discovery', 'Source-ready / PR-reviewed',
                     'Current-machine installation', 'Current-running-session reload',
                     'both Nix source and generated', 'deny-by-default', 'FLS-4',
                     'modules.dev.coding-agents.piSkills', 'it does not mutate',
                     '/Users/Jack/Code/archive/nix', 'git@github.com:jack-michaud/nix.git']:
            self.assertIn(text, ROLLOUT)

    def test_shell_examples_parse_and_do_not_bypass_or_operate(self):
        blocks = re.findall(r'```bash\n(.*?)```', ALL, re.S)
        self.assertGreater(len(blocks), 5)
        # A word boundary cannot start a whitespace-prefixed --flag. Match flags
        # separately, excluding word/hyphen prefixes and suffixes (e.g. --resume-extra).
        forbidden = (
            r'(?im)^\s*(?:unset\s|export\s+HERDR_|env\s+-u|'
            r'.*(?:\b(?:sudo|switch|restart|send-keys)\b|'
            r'(?<![\w-])--(?:delegate|resume)(?![\w-])))'
        )
        for block in blocks:
            self.assertNotRegex(block, forbidden)
            subprocess.run(['bash', '-n'], input=block, text=True, check=True, capture_output=True)
        self.assertEqual(sum('coordinator tell "$relay"' in b for b in blocks), 1)
        self.assertNotRegex('\n'.join(blocks), r'(?m)^.*(?:board|herdr-projects).*\b(?:set|unset|add|delegate|approve)\s')


class SafetyLintRegressionTest(unittest.TestCase):
    def lint_with_example(self, example):
        # Inject inert documentation only; bash -n parses but never executes it.
        document = ALL + '\n```bash\n' + example + '\n```\n'
        with patch.dict(globals(), {'ALL': document}):
            SkillContractTest().test_shell_examples_parse_and_do_not_bypass_or_operate()

    def test_forbidden_examples_are_rejected_by_actual_document_lint(self):
        for example in [
            'pi --resume "$live_session"',
            'pi --resume="$live_session"',
            'pi "--resume" "$live_session"',
            '  pi\t--resume "$live_session"',
            'helper --delegate "$task"',
            'unset HERDR_PANE_ID',
        ]:
            with self.subTest(example=example):
                with self.assertRaisesRegex(AssertionError, 'Regex matched'):
                    self.lint_with_example(example)

    def test_safe_flag_prefixes_are_not_rejected_as_exact_forbidden_flags(self):
        for example in ["printf '%s\\n' --resume-extra", "printf '%s\\n' --delegate-extra"]:
            with self.subTest(example=example):
                self.lint_with_example(example)


@unittest.skipUnless(os.environ.get('HERDR_CLI_CHECKS') == '1', 'opt in to installed help/version checks')
class InstalledSyntaxTest(unittest.TestCase):
    def run_cli(self, argv):
        result = subprocess.run(argv, capture_output=True, text=True, timeout=20, check=True)
        return result.stdout + result.stderr

    def test_board_help_advertises_taught_interfaces(self):
        board = os.environ.get('HERDR_PROJECTS_BIN', str(Path.home() / '.herdr-projects/data/bin/herdr-projects'))
        version = self.run_cli([board, 'version'])
        self.assertRegex(version, r'herdr-projects \d+\.\d+\.\d+')
        help_text = self.run_cli([board, '--help'])
        for syntax in ['coordinator --machine', 'coordinator --project REPO', 'coordinator tell <text>',
                       'autopilot', 'machines', 'show [<id>]', '--json']:
            self.assertIn(syntax, help_text)
        print(version.strip())

    def test_herdr_help_advertises_exact_safe_commands(self):
        self.assertRegex(self.run_cli(['herdr', '--version']), r'herdr \d+\.\d+\.\d+')
        for args, expected in [
            ('machine list', '--json'), ('machine status', '--json'),
            ('pane current', '--current'), ('pane list', '--workspace'),
            ('pane process-info', '--pane'), ('agent list', 'List agents'),
            ('agent get', '<target>')]:
            with self.subTest(args=args):
                self.assertIn(expected, self.run_cli(['herdr', *shlex.split(args), '--help']))
        self.assertIn('--machine', self.run_cli(['herdr', '--help']))


if __name__ == '__main__':
    unittest.main()
