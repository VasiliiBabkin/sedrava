> Historical reference; not a current release or installation guide. [Current Rust documentation](README.ru.md).

# The original idea behind Sedrava

## Origin (author's recollection)

Around 2011, the author vividly dreamed of a programming language for Windows in which a short instruction such as:

```text
make.window
```

would immediately produce a working windowed application. At the time, the author did not have the technical knowledge or AI assistance to implement the concept. The approach remained memorable: express the desired result directly, and let the language perform the implementation work.

This is a recollection and design inspiration, not a claim that the syntax or an implementation existed in 2011.

## Guiding principle

**Describe the application; get the application.**

Sedrava should prioritize:

1. **Minimal ceremony.** Common application structures should require very little source code.
2. **Immediate visible results.** The simplest valid description should build and run without handwritten platform boilerplate.
3. **Declarative sedrava.** Describe what the app should be and do, rather than manually constructing every platform detail.
4. **Portable meaning.** One source should target multiple platforms while retaining consistent behavior.
5. **Honest defaults and explicit control.** Defaults should make simple things simple, while advanced capabilities remain available and security constraints remain visible.

## Long-term direction

The dream's `make.window` is a useful benchmark for simplicity, **not yet an implemented Sedrava instruction**. A future Windows backend and minimal window/application declaration could realize it, alongside Android and Web. Do not advertise Windows EXE generation until a backend, build pipeline, and tests exist.

The goal is not to remove all complexity by hiding critical behavior; it is to remove unnecessary complexity from the author's path to a working program.
