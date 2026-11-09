# Selective native delegation

Registered LLM workers remain the default for ordinary research, drafts,
implementation, candidate tests, execution, analysis and routine review.
Native delegation is permitted for EGM's fresh-context reviewers, difficult
architectural trade-offs, rigorous reasoning/proofs, complex root-cause analysis,
or an explicitly requested stronger independent judgment. Delegate qualifying
independent reasoning/review tasks to native agents when useful without asking
the user to request each agent. Choose the route within this policy; the user
need not name a worker on each task.
Do not classify every task as difficult. Missing permissions, inputs, a gateway
failure or a worker timeout alone do not justify replacing managed execution.

Before spawning native agents, briefly state the reason, narrow scope and
expected output. Keep their count and repeated rounds bounded. Native agents
use the main client's configured account/models; they are not DeepSeek/Qwen
worker tasks and may consume additional account usage. They are outside the
managed pool's backend admission limit and task result/cancellation interface.

Use native agents for reasoning and review with read-only source access by
instruction. Give them exact input paths/revisions and explicit constraints.
Have them return findings; the main writes requested design/report artifacts.
Do not let native agents edit the original checkout or managed worktrees, alter
Git state, or share implementation files with workers. Product code changes go
through managed tasks with independent validation. Read-only instructions do
not create a separate sandbox; existing host permissions remain authoritative.
Wait for actual completion, report failed/missing reviews, and close agents
when finished. Do not label native reports as worker-task succeeded results.

For EGM, follow the installed plugin's personas, standards, stage dependencies
and user approval gates. Use fresh contexts and pass only explicit review inputs,
not the parent transcript or its conclusions. In Codex use fork_context=false
or fork_turns="none" when the actual tool schema offers it. This does not prove
that host instruction files were excluded. Do not invent unavailable tools or
claim a Goldfish review without fresh-context delegation. The plugin must be
installed separately. Only its main/synthesizer writes requested report artifacts.

Native Agent/Task and skills may be used in this mode; Claude Workflow/TeamCreate
and starting another main from Bash remain restricted by the kit. Existing
caller deny/ask rules and sandbox settings are not removed. This session's
launcher mode refines older blanket native-delegation bans in kit
project templates; it does not waive the task's protection or approval rules.
