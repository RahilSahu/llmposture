# LLM Security Research Notes

This document records the research base behind LLMPosture: the risk taxonomy it
maps to, the published attack techniques its probe packs are modelled on, and a
table of real, verified CVEs in LLM applications and frameworks that show why
these flaws matter in production. Every CVE listed here was checked against the
NVD record or the vendor / GitHub Security Advisory for that identifier during
the research pass (November 2026). Rumoured identifiers that could not be
verified were left out on purpose.

## 1. Taxonomy: OWASP Top 10 for LLM Applications (2025)

LLMPosture maps every probe to the OWASP Top 10 for LLM Applications, 2025
edition (OWASP GenAI Security Project, released 18 November 2024). The ten
entries, with their exact names:

| ID | Name |
| --- | --- |
| LLM01:2025 | Prompt Injection |
| LLM02:2025 | Sensitive Information Disclosure |
| LLM03:2025 | Supply Chain |
| LLM04:2025 | Data and Model Poisoning |
| LLM05:2025 | Improper Output Handling |
| LLM06:2025 | Excessive Agency |
| LLM07:2025 | System Prompt Leakage |
| LLM08:2025 | Vector and Embedding Weaknesses |
| LLM09:2025 | Misinformation |
| LLM10:2025 | Unbounded Consumption |

Source: OWASP GenAI Security Project, "OWASP Top 10 for LLM Applications
2025", https://genai.owasp.org/llm-top-10/

A behavioural scanner like LLMPosture can test the categories that show up in
model responses: LLM01, LLM02, LLM05, LLM06 and LLM07 directly, and LLM08
partially (through indirect injection carried in retrieved content). LLM03,
LLM04, LLM09 and LLM10 are supply-chain, training-time, or volumetric risks
that a prompt-level scanner cannot honestly measure, so LLMPosture does not
claim probes for them.

### MITRE ATLAS mapping

MITRE ATLAS (Adversarial Threat Landscape for Artificial-Intelligence
Systems, https://atlas.mitre.org) catalogues the same behaviours as adversary
techniques. The mappings LLMPosture uses:

| ATLAS technique | Meaning | LLMPosture probe packs |
| --- | --- | --- |
| AML.T0051 LLM Prompt Injection (incl. .000 Direct, .001 Indirect) | Crafted input steers the model away from its intended behaviour | Direct injection, indirect injection, encoding bypass |
| AML.T0054 LLM Jailbreak | Prompts that defeat the model's safety or policy controls | Jailbreak resistance |
| AML.T0056 LLM Meta Prompt Extraction | Extracting the system / meta prompt | System prompt leakage |
| AML.T0057 LLM Data Leakage | Eliciting data the model should not disclose | Sensitive information disclosure |
| Excessive agency (ATLAS groups this under LLM application exploitation techniques) | Getting the model to misuse connected tools or act without confirmation | Excessive agency simulation |

## 2. Published attack techniques behind the probe packs

LLMPosture probes are modelled on peer-reviewed or vendor-published research.
In line with the project's safety design, every technique is re-aimed at a
benign canary (a marker string, a planted fake secret, a fake tool), never at
real harmful output.

- **Instruction override and hierarchy attacks.** The baseline direct
  injection: "ignore previous instructions", fake system messages, delimiter
  and context switching. Documented since the earliest prompt-injection
  write-ups and formalised in Greshake et al. (below).
- **Indirect prompt injection.** Greshake, Abdelnabi, Mishra, Endres,
  Holz and Fritz, "Not what you've signed up for: Compromising Real-World
  LLM-Integrated Applications with Indirect Prompt Injection" (2023),
  arXiv:2302.12173. Instructions hidden in retrieved documents, web pages or
  tool output are followed as if they were the user's. Basis for the
  `indirect_injection` pack (LLM01, ATLAS AML.T0051.001).
- **Universal adversarial suffixes (GCG).** Zou, Wang, Carlini, Nasr,
  Kolter and Fredrikson, "Universal and Transferable Adversarial Attacks on
  Aligned Language Models" (2023), arXiv:2307.15043. Optimised gibberish
  suffixes that transfer across models. LLMPosture includes the *shape* of
  this attack (a nonsense suffix appended to a canary request) without
  reproducing optimised suffixes.
- **PAIR and TAP.** Chao et al., "Jailbreaking Black Box Large Language
  Models in Twenty Queries" (PAIR, 2023), arXiv:2310.08419; Mehrotra et
  al., "Tree of Attacks: Jailbreaking Black-Box LLMs Automatically" (TAP,
  2023), arXiv:2312.02119. Automated attacker-LLM loops. LLMPosture ships
  hand-written probes in this spirit; it does not run an automated attacker
  loop against third-party models.
- **Crescendo.** Russinovich, Salem and Eldan (Microsoft), "Great, Now
  Write an Article About That: The Crescendo Multi-Turn LLM Jailbreak
  Attack" (2024), arXiv:2404.01833. Benign-seeming turns escalate gradually.
  Basis for the multi-turn probes in the `jailbreak` pack.
- **Many-shot jailbreaking.** Anthropic, "Many-shot Jailbreaking" (April
  2024), https://www.anthropic.com/research/many-shot-jailbreaking. Long
  contexts filled with fake compliant Q&A pairs prime the model to comply
  once more. Basis for the many-shot style probe.
- **Skeleton Key.** Microsoft Security Blog, "Mitigating Skeleton Key, a
  new type of generative AI jailbreak technique" (June 2024). Asks the
  model to augment rather than refuse, with a warning-prefix framing.
- **Encoding and obfuscation bypasses.** Base64, ROT13, leetspeak, reversed
  text, homoglyphs, and payload splitting are catalogued in the OWASP LLM01
  guidance and in most red-team write-ups since 2023. Basis for the
  `encoding` pack.
- **ASCII smuggling and Unicode tag characters.** Riley Goodside's and
  Johann Rehberger's 2024 write-ups on Unicode Tag block characters
  (U+E0000 to U+E007F) that render invisibly in most UIs while remaining
  visible to the model, used to smuggle instructions and to hide exfiltration
  links. Basis for the tag-character probe and the markdown-image exfiltration
  probes in `output_handling`.
- **Prompt leakage.** A large body of 2023 to 2025 work on extracting system
  prompts (repeat-the-context, translation, debug-mode and completion
  framings) motivates the `system_prompt_leakage` pack (LLM07, ATLAS
  AML.T0056). OWASP promoted system prompt leakage to its own category in
  the 2025 list for exactly this reason.
- **Retrieval and memory poisoning.** PoisonedRAG (Zou et al., USENIX
  Security 2025) showed that a small number of poisoned passages in a
  retrieval corpus can steer a RAG system's answers, because the model
  treats retrieved text as ground truth. The same trust problem appears in
  assistants with long-term memory: instructions or false facts planted in
  one session, or loaded from a poisoned store, are honoured in later
  sessions as if the operator had written them. Basis for the `rag_memory`
  pack (LLM08, with LLM01 for the instruction-following half): poisoned
  passages, planted false memories carrying a canary recovery code,
  citation laundering, conflicting sources, and a memory
  write-then-trigger pair.

## 3. Verified CVEs in LLM applications and frameworks

These are real vulnerabilities in the software that wraps LLMs. Most of them
are prompt-injection-to-impact chains: the model was steered, and the
application then executed, queried, fetched or rendered whatever came back.
That is the exact failure shape LLMPosture's agency and output-handling packs
simulate with fake tools and canary tokens.

| CVE | Product | Description |
| --- | --- | --- |
| CVE-2023-29374 | LangChain (through 0.0.131) | LLMMathChain allowed prompt injection that executed arbitrary Python via `exec`; CVSS 9.8. NVD; NVIDIA AI Red Team write-up. |
| CVE-2023-32785 | LangChain | SQLDatabaseChain enabled SQL injection through crafted prompts. NVIDIA AI Red Team disclosure. |
| CVE-2023-32786 | LangChain | APIChain enabled server-side request forgery through crafted prompts. NVIDIA AI Red Team disclosure. |
| CVE-2023-39662 | LlamaIndex (0.7.13 and earlier) | PandasQueryEngine executed LLM output via `exec`, giving remote code execution through prompt injection; CVSS 9.8. NVD / OSV (GHSA-2xxc-73fv-36f7). |
| CVE-2024-3098 | LlamaIndex | Prompt injection in `exec_utils.safe_eval` bypassed the CVE-2023-39662 fix and again reached arbitrary code execution. GHSA-wvpx-g427-q9wc. |
| CVE-2025-3248 | Langflow (before 1.3.0) | Unauthenticated remote code execution in the `/api/v1/validate/code` endpoint; CVSS 9.8; listed in CISA KEV and exploited in the wild. NVD. |
| CVE-2025-59528 | Flowise | CustomMCP node parsed a user-supplied MCP server config with `eval`, giving unauthenticated JavaScript code execution; CVSS 10.0. GitHub Security Advisory. |
| CVE-2025-61913 | Flowise (before 3.0.8) | Path traversal in the ReadFileTool and WriteFileTool components allowed authenticated attackers to read and write arbitrary files; CVSS 9.9. GHSA-jv9m-vf54-chjj. |
| CVE-2026-41264 | Flowise (before 3.1.0) | CSV Agent node evaluated an LLM-generated Python script without sandboxing, so prompt injection reached host code execution. NVD. |
| CVE-2026-69253 | Flowise (before 3.1.3) | Custom-tool components interpolated a user-controlled `baseURL` into JavaScript run in the vm2 sandbox, enabling code injection and sandbox escape. GHSA-wg86-r78f-74mp. |
| CVE-2025-46719 | Open WebUI (before 0.6.6) | HTML tags in chat messages were rendered unsafely, allowing stored JavaScript injection into shared chat transcripts (stored XSS, token theft, chained admin compromise). NVD / GHSA-9f4f-jv96-8766. |
| CVE-2025-64495 | Open WebUI (0.6.34 and below) | DOM XSS: custom prompt bodies were assigned to `innerHTML` without sanitisation when "Insert Prompt as Rich Text" was enabled. NVD / GHSA-w7xj-8fx7-wfch. |
| CVE-2025-64496 | Open WebUI (before 0.6.35) | Direct Connections let a malicious external model server inject server-sent events that executed JavaScript in the victim's browser, enabling account takeover. Cato Networks research; NVD. |

Pattern worth noticing: in LangChain, LlamaIndex and Flowise, the model was
not the vulnerability. The vulnerability was an application that treated
model output as trusted code, SQL, URLs, file paths or HTML. Behavioural
testing of the model (does it follow injected instructions, does it leak,
does it call tools without confirmation, does it emit raw markup) is how you
find the steering half of those chains before someone else does.

## 4. How the research maps to probe packs

| Probe pack | OWASP | ATLAS | Research basis |
| --- | --- | --- | --- |
| direct_injection | LLM01:2025 | AML.T0051.000 | Instruction override literature; Greshake et al. |
| indirect_injection | LLM01:2025 (LLM08 adjacent) | AML.T0051.001 | Greshake et al. 2023; Rehberger's exfiltration write-ups |
| jailbreak | LLM01:2025 | AML.T0054 | Crescendo; many-shot; Skeleton Key; PAIR/TAP (manual probes); GCG shape |
| encoding | LLM01:2025 | AML.T0051 | OWASP LLM01 obfuscation guidance; ASCII smuggling research |
| system_prompt_leakage | LLM07:2025 | AML.T0056 | Prompt-leakage research; OWASP LLM07 |
| sensitive_disclosure | LLM02:2025 | AML.T0057 | OWASP LLM02; planted-secret extraction tests |
| excessive_agency | LLM06:2025 | Tool abuse class | OWASP LLM06; LangChain/Flowise tool CVE pattern |
| output_handling | LLM05:2025 | Output handling class | OWASP LLM05; Open WebUI XSS CVEs; markdown-image exfiltration research |
| rag_memory | LLM08:2025 / LLM01:2025 | AML.T0051.001 adjacent | PoisonedRAG (Zou et al. 2025); persistent-memory poisoning demonstrations |

## 5. Method and limits of this research

CVE entries were verified against NVD records or the corresponding GitHub
Security Advisories in November 2026; scores quoted are the CNA or NVD base
scores from those records. Attack-technique summaries are drawn from the
papers and vendor posts cited. LLMPosture's probes test model behaviour with
benign canaries only; the scanner does not ship, and this document does not
reproduce, working exploit payloads for the CVEs above.
