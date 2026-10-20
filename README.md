# Disciples 2 freezes on the neutral turn: fix for DisciplesGL on 120/144/165/240 Hz monitors

Fix for **Disciples II: Rise of the Elves** (GOG / Steam, v3.01) freezing or hanging during the
AI / neutral turn when the game uses the **DisciplesGL** OpenGL wrapper (`C4dll-R.dll`) on a
high-refresh-rate monitor.

## Symptoms

- The game freezes ("Disciples II v3.01 is not responding") when it's the neutral player's turn
  and neutral stacks have units to move. Other turns work.
- Sometimes an empty **"Microsoft Visual C++ Runtime Library"** error box appears.
- The game uses a lot of memory (close to 2 GB) right before it freezes.
- It happens every time with the same save, and only on a 120 Hz+ monitor
  (confirmed at 240 Hz; the same code also fails at 120, 144, 165 and 360 Hz with some speed
  settings). It doesn't happen at 60 Hz.

## Cause

DisciplesGL (`C4dll-R.dll`, version 2.0.2) hooks the game's stack-movement animation to scale it
by its *GameSpeed* setting and the display refresh rate:

```
step = step * (fast ? 10 : 20) * GameSpeed / (3 * refreshRate)   // unsigned integer division
```

The game then halves the step up to twice. At 240 Hz with default speed settings this gives
`14 * 10 * 15 / 720 = 2 -> 1 -> 0`. With a step of 0 the game's animation loop
(`for (d = 0; d < length; d += step)`) never advances and keeps allocating until the 32-bit
process runs out of memory (~2 GB). The out-of-memory error then deadlocks the error dialog
against the audio thread, so the game freezes instead of crashing.

At 60 Hz the same formula gives a step of 3, which is why most people never see it. Testing the
real hook code shows a step of 0 with some speed settings at 120, 144, 165, 240 and 360 Hz, but
never at 60 or 75 Hz.

## Fix

`C4dll-R.dll` in this repo is DisciplesGL 2.0.2 with a 17-byte change: both exits of the speed
hook jump to a small routine that raises the step to at least 4 (so it stays >= 1 after the game's
two halvings), then continue exactly as before. Nothing else in the DLL changes, apart from the
`.text` section size and the PE checksum in the header.

Tested by running the hook's real machine code from both DLLs over 672 combinations
(refresh 60-360 Hz, GameSpeed 1x-3x, game speeds 1-3, both halving flags): the original ends with
a step of 0 in 46 of them, the patched DLL in none. Also confirmed in-game.

## Install

1. Check your DisciplesGL version. This fix is **only** for 2.0.2:
   - original `C4dll-R.dll` SHA-256: `4730a43e94d2f6a4ba512564cf58a4f0e3b8c0e927fe293a1504f30463fb2107`
   - patched `C4dll-R.dll` SHA-256: `cdd382c73137ee52a259c2b8871da61897ef52254283283d166d0af6559de874`
2. Back up `C4dll-R.dll` in your game folder (for example, rename it to `C4dll-R.dll.orig`).
3. Put the patched `C4dll-R.dll` in the game folder.

To undo, put your backup back.

### Or patch your own copy

```
python patch_c4dll.py C4dll-R.dll C4dll-R.patched.dll
```

The script only patches the exact 2.0.2 file: it checks the SHA-256 and the bytes at every patch
site, and stops without writing anything if they don't match. (The patch writes at fixed file
offsets, which would corrupt any other build.)

## Workarounds without replacing the DLL (not tested in-game)

- Run the game at 60 Hz.
- Set `PlayerSpeed=2` and `OpponentSpeed=2` in `Disciple.ini` (at 240 Hz the step then stays >= 1).
- Don't set the wrapper's `SpeedEnabled=0`: its other formula reaches 0 even sooner.

## Details

| | Address |
|---|---|
| Game: animation-point loop | `Discipl2.exe` 0x4f5b8d (loop at 0x4f5d8c) |
| Game: call DisciplesGL replaces | 0x4f5d59 `call 0x61a5fd` |
| DisciplesGL hook | `C4dll-R.dll` RVA 0x130f0 -> 0x13080 |
| Patched exits | RVA 0x130bd, 0x130e3 -> new code at RVA 0x35740 |

`test/hooktest.c` loads a `C4dll-R.dll` without running its startup code, calls the hook the way
the game does, and reports which settings end with a step of 0. Build it as 32-bit
(e.g. `zig cc -target x86-windows-gnu test/hooktest.c -o hooktest.exe`) and run
`hooktest.exe C4dll-R.dll`.

Found by reverse engineering the game and wrapper with Ghidra and a memory dump of the frozen
process, with help from Claude.

DisciplesGL is not my project; all credit for the wrapper goes to its author. This repo only
fixes one bug in it.
