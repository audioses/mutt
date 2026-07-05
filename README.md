# MUTT

**Multi-Use Translation Toolkit**

*A translation tool that adapts to you — not the other way around.*

---

## What is MUTT?

MUTT is a desktop translation application.

You open a file → translate it (with AI, without AI, or both) → save the result.

It’s not a full CAT suite. It doesn’t try to be.

It’s a **power-user translation tool** built for people who want control:
- Choose your own AI provider
- Run models locally or online
- Write your own prompts
- Define your own workflow

No lock-in. No subscriptions. No assumptions about how you should work.

---

## Quick start

Prebuilt Windows builds are published on the [Releases page](https://github.com/audioses/mutt/releases) on every update.

Or run from source:

```bash
git clone https://github.com/audioses/mutt.git
cd mutt
pip install -r requirements.txt
python main.py
````

Then:

1. Open a file
2. Choose your translation method (AI / offline / manual)
3. Start translating

That’s it.

---

## The story behind this

I'm visually impaired. I studied translation and interpreting.

If you've ever used a CAT tool — Computer-Assisted Translation — you know how they work. You learn their interface. You memorize their shortcuts. You adapt to their workflow. And they still do things their way, not yours.

Now imagine that, but you can’t see the screen.

I spent years forcing tools like Trados and MemoQ to be usable. Hacks, scripts, keyboard gymnastics. I’d finally get into a rhythm — and then an update would break everything. New UI. New layout. New accessibility issues.

Every fix was temporary.

At some point it clicked:

You feed them time, effort, money — and they still act like they own you.

You can’t make a cat obey you. You just serve it.

So I asked a different question:

What if translation tools were more like dogs?

Loyal. Adaptable. By your side — not in your way.

I switched to software development and built that.

First for myself. Then for anyone else who wants it.

---

## What MUTT supports

### File formats

MUTT works with the formats translators actually deal with:

* **PO / POT**
* **XLIFF**
* **JSON**
* **CSV**
* **Plain text**
* **HTML**
* **Word (.docx)**
* **Excel (.xlsx)**
* **PowerPoint (.pptx)**

All formats preserve structure. You get back what you put in — translated.

---

### AI providers (bring your own)

No lock-in. Use what you want:

* **OpenAI**
* **Google Gemini**
* **OpenRouter**
* **Any OpenAI-compatible API** (Groq, Together, vLLM, Ollama, etc.)
* **Local models** (Llama.cpp, LM Studio)

Or skip AI entirely:

* **Argos Translate** (offline)
* **HuggingFace models** (local transformers)

No internet required for offline modes.

---

### Translation modes

* **AI translation** — batch processing with full control over size, tokens, and context
* **Manual translation** — just type
* **Review mode** — step through entries one by one
* **Mixed workflows** — use AI where it helps, ignore it where it doesn’t

---

### The toolbox

While reviewing translations, MUTT gives you contextual AI tools:

* Generate variations
* Explain differences
* Check grammar and errors
* Analyze cultural context
* Free-form chat with full entry context
* Etymology lookup

You can also create your own tools using simple YAML configs — no coding required.

---

### Prompt system

You’re not stuck with predefined prompts.

* Create your own prompts
* Save and reuse them
* Tailor them per project or domain

During batch translation, you control how the AI behaves. Not the other way around.

---

### Workflow features

* **Project files (.mutt)** — save and resume everything
* **Autosave + crash recovery** — snapshots every 30 seconds
* **Translation memory** — simple, persistent JSON-based storage
* **Search + navigation** — jump anywhere instantly
* **Exclusion rules** — skip ranges during translation

---

### Keyboard-first design

The entire app is keyboard-driven.

Not as an accessibility feature — as the primary interface.

* Navigate entries
* Edit translations
* Search, jump, and control everything

For some users, this is convenience. For others, it’s the difference between usable and unusable.

---

## What MUTT is not

Being clear matters more than overselling.

MUTT does **not** include:

* Enterprise-grade translation memory (no fuzzy matching engine)
* Alignment tools
* Terminology databases (basic glossaries only)
* Multi-user collaboration
* Tag protection systems
* Workflow automation / approval chains
* Plugin architecture
* Multi-file project batching (yet)

If you need those, tools like Trados or MemoQ exist for a reason.

MUTT doesn’t compete there.

It competes on:

* flexibility
* cost (free)
* and the ability to make the tool work *your way*

---

## Who this is for

* Freelance translators who want AI without paying for CAT tools
* Localizers working with real-world file formats
* Power users who want full control over AI and workflow
* Translators with accessibility needs
* Developers translating app content
* Anyone priced out of traditional tools

---

## The name

CAT tools have dominated translation for decades.

They’re the purebreds:

* polished
* expensive
* rigid

MUTT is the mixed breed.

Not as fancy. Not as polished.

But adaptable, loyal, and a lot easier to live with.

Train it, and it works for you.

That’s the idea.

---

## Status

Actively used in real translation work.

Single-developer project, so updates are incremental.

Core features are stable:

* file handling
* AI integration
* batch processing
* crash recovery

Expect rough edges in less-used areas.

Open source under the MIT License.

---

## Contributing

Bug reports, feature requests, and pull requests are welcome.

If you're a translator and something doesn’t behave the way you expect — that’s a bug.

---

*Built by a translator who became a developer — because the tools that existed weren’t worth adapting to.*

