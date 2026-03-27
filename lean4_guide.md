# Lean 4 Setup and Verification Guide

This guide explains how to set up Lean 4 for the first time and verify that it is working in this repository.

## 1. Prerequisites

On macOS, make sure these tools are available:

```bash
command -v git
command -v curl
```

If either command is missing, install Xcode Command Line Tools first:

```bash
xcode-select --install
```

## 2. Install Lean via elan (first-time setup)

Install `elan` (Lean toolchain manager):

```bash
curl https://elan.lean-lang.org/elan-init.sh -sSf | sh
```

Reload your shell (zsh):

```bash
source ~/.zshrc
```

Verify installation:

```bash
elan --version
lean --version
lake --version
```

## 3. Verify this repository Lean workspace

From the repository root:

```bash
cd lean_workspace
```

Check expected Lean project files:

```bash
ls -la
```

You should see at least:
- `lean-toolchain`
- `lakefile.toml` or `lakefile.lean`
- Lean source files such as `Main.lean` and `LeanEcon.lean`

Resolve dependencies and build:

```bash
lake update
lake build
```

If the build succeeds, the project is configured correctly.

## 4. Run hello world

Run the executable target defined in `lakefile.toml`:

```bash
lake exe leanecon
```

Expected output:

```text
Hello, world!
```

## 5. Additional checks

Run Lean in the project environment:

```bash
lake env lean --version
```

This confirms the workspace is using the toolchain pinned by `lean-toolchain`.

## 6. Common issues

- `lake build` says no configuration file:
  The folder is missing `lakefile.toml` or `lakefile.lean`.

- `lean` or `lake` command not found:
  `~/.elan/bin` is not on your PATH yet. Reload shell and try again.

- Wrong executable name in `lake exe`:
  Use the executable name from `[[lean_exe]] name = "..."` in `lakefile.toml`.
