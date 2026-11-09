# ZenOS shell defaults

The default Powerlevel10k configuration is copied from
`zenos-old/src/users/doromiert/resources/p10k.zsh`. Personal Git identity and
machine-specific directories are intentionally not part of the system default.

## Automatic Nix progress

`zenos-nix` runs the original Nix executable once. In an interactive terminal,
`build`, `run`, `shell`, `env shell`, `develop` and `copy` send their separate
`json-log-path` socket events to nix-output-monitor. App stdin/stdout/stderr are
inherited, and the frontend execs real Nix, retaining its arguments, PID, signal
handling and exit status. No target pre-build or second evaluation is performed.
The progress sidecar closes when Nix releases its log socket at app handoff.
Nix 2.34.8 and nix-output-monitor 2.2.0 are tested.

Noninteractive commands, completion, explicit JSON/raw/log output and unsupported
commands run unchanged. `command nix ...` bypasses the interactive shell function;
`ZENOS_NOM=0 nix ...` disables the monitor for one invocation. No process-wide Nix
configuration or replacement `nix` binary is installed, so scripts retain raw Nix.

`zenos-nix-monitor --rebuild COMMAND ...` monitors a rebuild helper which forwards
Nix options, preserving connections across its multiple Nix invocations. The
rebuild launcher supplies a duplicate terminal fd in `ZENOS_NOM_TTY_FD` so progress
avoids its original diagnostic log pipeline. This fd is private to that invocation.
