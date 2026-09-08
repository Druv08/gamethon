# Adaptive Enemy AI

**Explainable wave-to-wave adaptive strategy AI using behavioural analysis, utility scoring and online strategy learning.**

It is not a neural network, and it is not machine learning in the sense that
phrase usually implies. There is no model, no training set, no inference, and
nothing leaves the process. The whole learned state is six floating-point
numbers, and every decision it makes can be printed in a sentence and argued
with. That is the point: an opponent whose reasoning you cannot inspect is one
you cannot balance, and a five-wave run does not produce enough data to train
anything larger honestly.

The system runs entirely in C++ inside the game. No Python, no service, no API.

---

## Contents

1. [How it fits together](#how-it-fits-together)
2. [What is tracked](#what-is-tracked)
3. [Lane metrics](#lane-metrics)
4. [Lane vulnerability](#lane-vulnerability)
5. [Guard dominance](#guard-dominance)
6. [Enemy type effectiveness](#enemy-type-effectiveness)
7. [The strategies](#the-strategies)
8. [Choosing a strategy](#choosing-a-strategy)
9. [Reward and online learning](#reward-and-online-learning)
10. [Seeded randomness](#seeded-randomness)
11. [Fairness rules](#fairness-rules)
12. [Restart and New Game](#restart-and-new-game)
13. [A worked example](#a-worked-example)
14. [Inspecting it while it runs](#inspecting-it-while-it-runs)
15. [Why this is explainable adaptive AI](#why-this-is-explainable-adaptive-ai)

---

## How it fits together

Two world subsystems, both created automatically with the world and destroyed
with it.

| Class | File | Job |
|---|---|---|
| `UPTKAnalyticsSubsystem` | `Public/Analytics/PTKAnalyticsSubsystem.h` | Watches the wave, records what happened, scores it |
| `UPTKAdaptiveDirector` | `Public/Analytics/PTKAdaptiveDirector.h` | Reads the record, decides how the next wave attacks |

The cycle, once per wave:

```
wave begins   -> analytics opens a fresh set of counters
   ...        -> events arrive: damage, kills, spawns, deaths, possession
wave cleared  -> analytics scores and FREEZES a snapshot
              -> director scores that snapshot into a reward
              -> director updates the value of the strategy that ran
intermission  -> director builds the NEXT plan and the HUD shows it
next wave     -> wave manager spawns according to that plan
```

Adaptation happens **only** at the intermission. Nothing re-steers a horde that
is already on the field.

---

## What is tracked

Everything is event-driven. `GetAllActorsOfClass` is never called; the set of
live enemies is maintained by the spawn and death events themselves.

**Per guard, per wave** (`FPTKGuardWaveStats`)

- `PlayerControlledSeconds` and `PlayerControlFraction` — **human possession only**
- `TimesSwitchedInto`, `DamageDealt`, `Kills`, `DamageTaken`
- `bAlive`, `HealthFraction`, `bReceivedKingPower`
- `Dominance` (computed at freeze)

A guard that walked across the map on its own to help a neighbour was doing that
by itself. Counting it as player behaviour would make the AI's own assistance
look like a habit of the player's, which is precisely what later stages try to
read.

**Switching** (`FPTKSwitchStats`)

- `TotalSwitches`, `SwitchesPerMinute`, `AverageSecondsBetween`
- `Tempo` — `Low` at or below **4/min**, `High` at or above **12/min**, `Medium` between
- `bSingleGuardFocus` — true when one guard held **≥ 70%** of player-control time

Only two things are sampled rather than evented, because they are questions
about position rather than about something that happened: which lane a guard is
standing in, and how far the deepest enemy has advanced. Both are sampled every
**0.5 s** (`SampleInterval`), against a cached list.

---

## Lane metrics

Per lane, per wave (`FPTKLaneWaveStats`):

| Field | Meaning |
|---|---|
| `EnemiesSpawned`, `EnemyKills` | traffic and how much of it died |
| `DeepestProgress` | furthest any enemy on this lane got toward the core, 0–1 |
| `PlayerPresenceSeconds` | seconds the **player-driven** guard stood within 600 uu of the lane |
| `AIAssistPresenceSeconds` | seconds an **AI guard in the Assist state** did |
| `GuardDamageTaken`, `BaseDamageTaken` | punishment absorbed |
| `bBaseDestroyed`, `bBreached` | breached at `DeepestProgress ≥ 0.85` |
| `KingDamageFromLane` | core damage charged to the lane the attacker walked in on |

`PlayerPresence` and `AIAssistPresence` are deliberately **separate numbers**. A
lane the player personally defended and a lane the AI covered for them look
identical if the two are summed, and they mean opposite things about what the
player is actually doing.

---

## Lane vulnerability

Normalised 0–1. Every factor is clamped to 0–1 **before** it is weighted, so the
most any single factor can contribute is its own weight — a destroyed base is
serious, but it cannot by itself pin the score at 1.0 and hide everything else
about the lane.

```
Vulnerability =
      0.25 * clamp01(BaseDamageTaken / BaseMaxHealth)
    + 0.15 * clamp01(GuardDamageTaken / 2000)
    + 0.20 * clamp01(DeepestProgress)
    + 0.15 * (1 - PlayerPresenceShare)
    + 0.10 * (bBreached      ? 1 : 0)
    + 0.15 * (bBaseDestroyed ? 1 : 0)
```

`PlayerPresenceShare` is this lane's player presence over the wave's total.
`2000` is `GuardDamageReference` — damage has no natural ceiling the way a
health bar does, so the ceiling is chosen rather than derived.

**The untouched-lane rule.** A lane where nothing happened scores exactly `0.0`
and skips the formula entirely:

```
untouched = EnemiesSpawned == 0
         && BaseDamageTaken  == 0
         && GuardDamageTaken == 0
         && DeepestProgress  == 0
         && !bBaseDestroyed
```

Without it, every quiet lane would score on *low player presence* alone and the
metric would point at the calmest parts of the map. An earlier version keyed
this on the spawn count only, and scored a base that had lost most of its health
at `0.0` because nothing had been *dealt* onto that particular lane — a lane can
be hurt by enemies that arrived along a different route.

---

## Guard dominance

Normalised 0–1, computed per guard at freeze:

```
Dominance =
      0.30 * KillShare        (this guard's kills / all guard kills)
    + 0.30 * DamageShare      (this guard's damage / all guard damage)
    + 0.15 * Survival         (alive ? HealthFraction : 0)
    + 0.10 * PlayerUsage      (PlayerControlFraction)
    + 0.15 * LaneSuccess      (1 - vulnerability of the lane it defends)
```

**Player usage is deliberately the smallest term.** A guard the player drove all
wave but achieved nothing with is not the dominant guard, and defining dominance
by usage would say that it was. Usage colours the ranking; it does not decide it.

`LaneSuccess` is included so a guard that held a quiet line still reads as having
done its job, rather than being punished for having nothing to kill.

---

## Enemy type effectiveness

Per type, per wave. Damage terms are scored against the **best performer of that
wave** rather than an absolute number, so the scale stays meaningful whatever the
wave's size or composition.

```
Effectiveness =
      0.25 * share(DamageToGuards, best DamageToGuards this wave)
    + 0.25 * share(DamageToBases,  best DamageToBases  this wave)
    + 0.20 * share(DamageToKing,   best DamageToKing   this wave)
    + 0.10 * SurvivalFraction      (1 - Died/Spawned)
    + 0.20 * clamp01(DeepestProgress)
```

---

## The strategies

| Strategy | Used when | What it does |
|---|---|---|
| **Balanced Pressure** | no history, or nothing else fits | even weight on every lane |
| **Exploit Weak Lane** | a lane scored vulnerable | `Pressure = 1 + Vulnerability × 2.5` per lane — scaled, so the second-weakest lane also gets more than a safe one |
| **Counter Dominant Guard** | one guard is clearly ahead | re-mixes composition on that guard's lanes, and raises its lane traffic ×1.6 |
| **Split Pressure** | player camped one guard, or switches slowly | spreads across ≥ 3 **corners**, cap tightened to `1/(corners-1)` |
| **Breakthrough** | structures already damaged or breached | `1 + damage×2 + breached + destroyed×1.5`, favours Hijacker and Encrypter |
| **Focused Assault** | a weak lane the player is *not* defending | ×6 on that lane, cap raised to 55% |

Split spreads across **corners**, not merely lanes: two lanes out of the same
corner arrive together and can be met by one guard, which is exactly what the
strategy exists to defeat.

### The counter table

Biases, never rules. They **multiply** the wave's own composition weights on
that guard's lanes only, at ×2.0 for a favoured type and ×0.5 for a suppressed
one.

| Guard | More of | Less of | Reasoning |
|---|---|---|---|
| Wraith | Infiltrator, Encrypter | — | picks off single targets at range; numerous fast bodies and a heavy that survives the volley trouble it |
| Sentinel | Infiltrator, Encrypter | SwarmNode | splash is worth most against a tight crowd, so thin the crowd |
| Ravager | Exfiltrator, Encrypter | — | multi-target melee; ranged attackers make that reach matter less |
| Reaver | Exfiltrator, Encrypter | — | single-target melee, so the same answer applies harder |
| Aegis | Encrypter, Hijacker | SwarmNode | blocks outright while defending; sustained heavy pressure outlasts the shield rather than beating it |

Whoever led the last wave also gets a **light** version of this counter applied
regardless of the headline strategy, whenever a leader exists at all.

### Pressure caps

Normalised so all lanes sum to 1, then clipped: surplus above the cap is
redistributed to lanes still under it, repeated until it settles.

- Normal: **40%** max on one lane (`MaxLaneShare`)
- Focused Assault: **55%** (`MaxLaneShareFocused`)
- Split Pressure: tighter still — a 40% lane inside a "split" wave is not a split

Every lane keeps a non-zero floor, so no route ever becomes permanently safe.

---

## Choosing a strategy

```
Score(S) = Fit(S) × 0.55  +  LearnedValue(S) × 0.45
```

`Fit` is how well the strategy suits what the analytics currently say — a
utility score, recomputed every wave. `LearnedValue` is what the strategy has
been worth so far, and contributes nothing before there is any history.

Fit dominates deliberately, so a strategy cannot keep being chosen on past
success after the situation that suited it has passed.

Then, with probability **0.15** (`ExplorationChance`), the choice is replaced by
a uniformly random strategy and the plan is flagged `bExploratory`. That is what
lets a strategy which has never run still be reached.

---

## Reward and online learning

The reward is scored **from the horde's side** — it measures how well the
attacking plan did, not whether the game went well for the player.

```
Reward =
      0.22 * share(total guard damage taken, 4000)
    + 0.18 * (guards lost / guard count)
    + 0.22 * share(total base damage, 2500 × lane count)
    + 0.15 * (bases destroyed / 5)
    + 0.13 * clamp01(deepest lane progress)
    + 0.10 * share(King damage, 1500)
```

The update is a single line, applied once per wave to the strategy that ran it:

```
V  <-  V + LearningRate × (Reward - V)          LearningRate = 0.35
```

All six strategies start at `InitialStrategyValue = 0.5`. This is a bandit, not
a network: a few dozen bytes, converging within the handful of waves a run
actually has, and every number in it printable.

**Worked example, from a real run:**

```
Balanced Pressure  0.5000  ->  reward 0.130  ->  0.3705     (fell)
Counter Dom Guard  0.5000  ->  reward 0.623  ->  0.5432     (rose)
```

A reward *below* the current value lowers it; above, raises it. A reward of
0.285 against a 0.5 prior still **lowers** the value — "the wave went better
than the last one" and "the wave beat expectations" are different claims.

---

## Seeded randomness

The director seeds its own stream from the wave manager's run seed:

```
Stream.Initialize(WaveSeed ^ 0x5A17C0DE)
```

The XOR offset keeps the director's rolls from being the same sequence the wave
manager is already drawing from its own copy.

This gives two properties that are tested as opposites, and both matter:

| Test | Setup | Requirement |
|---|---|---|
| **Reproducibility** | same seed, **same** behaviour | decision must **match** |
| **A/B** | same seed, **different** behaviour | decision must **change** |

Passing only the second would be satisfied by a system that is merely random.
Passing only the first would be satisfied by one that ignores the player.

---

## Fairness rules

The director may alter exactly three things:

- **which lanes** get pressure
- **how much** each gets
- **what types** walk down them

It may not, and does not:

- raise enemy health or damage — those come from the wave's own scaling, applied
  to instances at spawn
- spawn extra enemies — the wave definition's `EnemyCount` builds a roster, and
  the director only decides where each of those bodies goes and what it is
- teleport anything, break lane rules, or redirect enemies across terrain
- re-steer a horde already on the field

An opponent that wins by quietly inflating its own numbers has not out-thought
the player, it has cheated. The distinction matters here more than the
difficulty does, and it is checked directly in the test suite: enemy health is
asserted to equal `base × wave scale` exactly.

---

## Restart and New Game

Adaptive state is **per run**. Both subsystems live in the world and die with
it, so a level reload clears the learned table and the wave history for free —
there is no reset code that can be forgotten.

| | Wave seed | Learned values | History |
|---|---|---|---|
| **Restart** | replayed (same run again) | cleared | cleared |
| **New Game** | freshly drawn | cleared | cleared |

Nothing is written to disk.

---

## A worked example

From an actual verification run, seed `24940`, both runs identical except for
how the player played:

**Run A — player held Wraith (98.5% of control time)**

```
[PTK Adaptive AI]
  Wave 2
  PlayerFocus=Wraith 0.99
  Switching=Low (2.9/min)
  WeakLane=SW_Sentinel 0.38
  DominantGuard=Wraith 0.60
  PreviousStrategy=Balanced Pressure
  Reward=0.16
  SelectedStrategy=Split Pressure
```

Composition bias: `NE_Wraith` → Infiltrator ×2.0, Encrypter ×2.0

**Run B — same seed, player held Ravager instead**

```
  PlayerFocus=Ravager
  SelectedStrategy=Split Pressure
```

Composition bias: `NE_Ravager` and `SE_Ravager` → Exfiltrator ×2.0, Encrypter ×2.0

The strategy is the same because the *kind* of behaviour was the same — the
player camped one guard in both runs, and the answer to that is to spread. But
the counter moved to a different guard on different lanes, purely because a
different guard was being camped.

---

## Inspecting it while it runs

**Between waves**, the HUD shows an `AI ANALYSIS` panel below the minimap:
player focus, weakest defence, strongest defender, previous strategy, enemy
success, the adaptation chosen, and what the next wave will do. Every line reads
a value the analytics actually computed — if something is not known yet, the
line is omitted rather than invented. It disappears on its own when the next
wave begins.

**`PTK.ToggleAIDebug`** opens a development panel with the full state: current
strategy and why it was chosen, the learned value and use count of all six
strategies, per-guard control share and dominance, per-lane vulnerability,
pressure and composition bias, switching classification, and the last reward.

**One log block per wave** is written when the next wave is decided — never per
tick, because a running commentary of the same numbers sixty times a second
buries the one moment that matters, which is the moment the decision changes.

---

## Why this is explainable adaptive AI

It adapts: the same seed produces different attacks depending on how the player
played, and the strategy values move with what actually worked.

It is explainable in a strong sense — not "we could add logging", but that the
reasoning *is* the implementation:

- every input is a named, printable quantity computed from a real game event
- every score is a weighted sum whose weights are visible, editable, and sum to 1
- the learned state is six numbers updated by one arithmetic line
- the choice is `fit × 0.55 + value × 0.45`, plus a flagged 15% exploration roll
- the plan carries its own reasoning strings, which are what the HUD displays

If it makes a decision that seems wrong, you can read the exact numbers that
produced it and change the weight that caused it. That property is worth more
here than the extra few percent of optimality a model might buy, and it is the
reason the design stops where it does.
