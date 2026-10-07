# Optional one-shot AI coach

OpenPoker Lab remains fully usable with external AI disabled. The question panel
always has a deterministic local fallback. An OpenAI request occurs only when
the local server is configured and the user checks **Use external AI for this
question** before asking.

## Local configuration

Set these environment variables in the same terminal that starts the server:

```powershell
$env:OPENPOKER_AI_COACH_ENABLED = "1"
$env:OPENAI_API_KEY = "<your project API key>"
$env:OPENAI_MODEL = "<a model enabled for your project>"
py -3 -m pokerlab.server
```

On macOS or Linux, use `export` for the same three variable names, then run
`python -m pokerlab.server`. The application does not choose a model or enable
external requests when any setting is missing. Keep the key in your local
environment; never add it to the repository or a saved hand.

To turn the integration off, stop and restart the server with
`OPENPOKER_AI_COACH_ENABLED` unset or set to `0`. The browser's per-question
checkbox starts unchecked and is unavailable until the server reports that all
three settings are present.

## What is sent

With the checkbox selected, the app sends the question, presentation settings,
and a versioned allowlist of facts from the selected saved decision. This bundle
includes your hero cards, the board, and saved decision facts. It excludes
opponent hole cards, the deck, names, notes, observation history, database/export
contents, and app conversation history. The model
returns only a structured plan; the local app validates it against trusted saved
evidence and renders every poker fact itself. Provider failures use a clearly
labeled local fallback.

The adapter uses the OpenAI Responses API with strict Structured Outputs, no
tools, a finite timeout and output limit, and `store: false`. See the official
[Responses API migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses)
for the `text.format` request shape and
[OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data)
for current retention details. `store: false` is an API request setting; it is
not a substitute for reviewing your organization's data controls.
