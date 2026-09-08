"""
Protect the King - 2D
Verifies the adaptive director: strategy selection, online learning, lane and
composition adaptation, pressure caps, fairness, and the same-seed A/B test.

The A/B test is the important one. It restarts with the SAME wave seed and
plays differently, so any change in the director's output can only have come
from the player's behaviour rather than from the dice.

RUN:
    UnrealEditor.exe <proj>.uproject -ExecutePythonScript=Tools/PTK_VerifyDirector.py -RenderOffscreen

Results: Tools/_Output/director_results.json
"""
import json
import time
import traceback
from pathlib import Path
import unreal

unreal.EditorPythonScripting.set_keep_python_script_alive(True)

OUT = Path(unreal.Paths.project_dir()) / "Tools/_Output"
OUT.mkdir(parents=True, exist_ok=True)

results = {}
notes = {}
done = False
stage = 0
started = time.monotonic()
run_started = time.monotonic()
world = None
run_a = {}
run_b = {}
seed_a = None
switch_timer = 0.0
switch_slot = 1

level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level.load_level('/Game/PTK/Maps/L_PTK_Battlefield')
level.editor_request_begin_play()


def check(name, condition, note=None):
    results[name] = bool(condition)
    if note is not None:
        notes[name] = note
    unreal.log('DIRECTOR | {} | {}'.format(name, 'PASS' if condition else 'FAIL'))


def actors(cls):
    return unreal.GameplayStatics.get_all_actors_of_class(world, cls)


def living(cls):
    return [a for a in actors(cls) if not a.is_dead()]


def key(text):
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    unreal.SystemLibrary.execute_console_command(world, text, pc)


def finish():
    global done
    safe = {}
    for k, v in notes.items():
        if isinstance(v, dict):
            safe[k] = {str(a): str(b) for a, b in v.items()}
        elif isinstance(v, (list, tuple)):
            safe[k] = [str(x) for x in v]
        else:
            safe[k] = v if isinstance(v, (int, float, bool, str)) else str(v)
    (OUT / 'director_results.json').write_text(json.dumps(
        {'results': results, 'notes': safe, 'run_a': run_a, 'run_b': run_b,
         'passed': sum(1 for v in results.values() if v is True),
         'failed': sorted(k for k, v in results.items() if v is not True)}, indent=2))
    done = True
    unreal.unregister_slate_post_tick_callback(callback)
    level.editor_request_end_play()
    unreal.SystemLibrary.quit_editor()


def plan_summary(plan, director):
    """A comparable, printable form of a decision."""
    return {
        'strategy': director.get_strategy_name(plan.strategy),
        'target_guard': str(plan.target_guard),
        'target_lane': str(plan.target_lane),
        'pressure': {str(l.lane_id): round(l.pressure, 3) for l in plan.lanes},
        'bias': {str(l.lane_id): {str(k): round(v, 2) for k, v in l.type_weights.items()}
                 for l in plan.lanes if len(l.type_weights) > 0},
        'reasoning': [str(r) for r in plan.reasoning],
    }


def hammer_lane(base_id, amount):
    """Damage one base so its lane must score vulnerable."""
    for b in actors(unreal.PTKGuardBase):
        if str(b.get_guard_id()) == base_id and not b.is_destroyed():
            b.debug_apply_damage(amount)


def clear_field():
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    for e in living(unreal.PTKEnemyCharacter):
        e.get_health_component().apply_damage(999999.0, pc.get_controlled_pawn())


def tick(delta):
    global stage, started, world, field, waves, director, analytics
    global seed_a, old_world, switch_timer, switch_slot
    try:
        if done:
            return
        elapsed = time.monotonic() - started
        if elapsed > 200 or (time.monotonic() - run_started) > 900:
            check('timeout at stage {}'.format(stage), False)
            finish()
            return

        # ---------------- RUN A: heavy Wraith use ----------------
        if stage == 0:
            world = editor.get_game_world()
            if not world or elapsed < 3:
                return
            pc = unreal.GameplayStatics.get_player_controller(world, 0)
            if not pc or not pc.get_controlled_pawn():
                return
            field = actors(unreal.PTKBattlefield)[0]
            waves = actors(unreal.PTKWaveManager)[0]
            director = field.get_director()
            analytics = field.get_analytics()
            check('Director subsystem exists', director is not None)
            if director is None:
                finish()
                return

            # Every strategy starts on the same value, so the first choice is
            # decided by fit alone rather than by a preloaded preference.
            values = [director.get_strategy_value(s) for s in [
                unreal.PTKStrategy.BALANCED_PRESSURE, unreal.PTKStrategy.EXPLOIT_WEAK_LANE,
                unreal.PTKStrategy.COUNTER_DOMINANT_GUARD, unreal.PTKStrategy.SPLIT_PRESSURE,
                unreal.PTKStrategy.BREAKTHROUGH, unreal.PTKStrategy.FOCUSED_ASSAULT]]
            check('Learning starts from a level table',
                  len(set(round(v, 3) for v in values)) == 1,
                  [round(v, 3) for v in values])
            key('Input.+key Enter')
            stage = 1
            started = time.monotonic()

        elif stage == 1:
            if elapsed < 0.8:
                return
            key('Input.-key Enter')
            seed_a = waves.get_active_seed()
            plan1 = director.get_current_plan()
            run_a['wave1'] = plan_summary(plan1, director)
            check('Wave 1 has no history, so pressure is balanced',
                  plan1.strategy == unreal.PTKStrategy.BALANCED_PRESSURE,
                  director.get_strategy_name(plan1.strategy))
            pressures = [l.pressure for l in plan1.lanes]
            check('Balanced pressure really is even',
                  max(pressures) - min(pressures) < 0.02,
                  {str(l.lane_id): round(l.pressure, 3) for l in plan1.lanes})
            check('Pressures sum to one', abs(sum(pressures) - 1.0) < 0.01,
                  round(sum(pressures), 4))

            # TEST A: play Wraith and only Wraith.
            unreal.GameplayStatics.get_player_controller(world, 0).select_guard_slot(3)
            stage = 2
            started = time.monotonic()

        elif stage == 2:
            if elapsed < 20:
                return
            # TEST B: one base badly hurt, and the player has been nowhere near it.
            hammer_lane('Sentinel', 2000.0)
            clear_field()
            stage = 3
            started = time.monotonic()

        elif stage == 3:
            if elapsed < 4 or len(analytics.get_snapshots()) == 0:
                return
            snap = analytics.get_snapshots()[0]
            check('Reward was scored for the wave that ran',
                  0.0 <= director.get_last_reward() <= 1.0,
                  round(director.get_last_reward(), 3))
            run_a['reward_wave1'] = round(director.get_last_reward(), 4)
            run_a['value_after_wave1'] = round(
                director.get_strategy_value(unreal.PTKStrategy.BALANCED_PRESSURE), 4)

            # TEST E/F: the value moved toward the reward it earned.
            before = 0.5
            reward = director.get_last_reward()
            after = director.get_strategy_value(unreal.PTKStrategy.BALANCED_PRESSURE)
            expected = before + 0.35 * (reward - before)
            check('Learned value moves toward the reward',
                  abs(after - expected) < 0.01,
                  'before {:.3f} reward {:.3f} -> after {:.3f} (expected {:.3f})'.format(
                      before, reward, after, expected))
            check('A poor reward lowers the value, a good one raises it',
                  (after < before) == (reward < before),
                  'reward {:.3f} vs start {:.3f}'.format(reward, before))
            check('Strategy use was counted',
                  director.get_strategy_uses(unreal.PTKStrategy.BALANCED_PRESSURE) == 1)
            stage = 4
            started = time.monotonic()

        elif stage == 4:
            # Wave 2's plan is built when wave 2 begins.
            if waves.get_current_wave() < 2:
                return
            plan2 = director.get_current_plan()
            run_a['wave2'] = plan_summary(plan2, director)
            run_a['focus'] = str(analytics.get_snapshots()[0].switching.focus_guard_id)

            check('Wave 2 reacts to wave 1 rather than repeating it',
                  plan2.wave_number == 2 and len(plan2.reasoning) > 0,
                  run_a['wave2']['reasoning'])

            pressures = [l.pressure for l in plan2.lanes]
            cap = 0.55 if plan2.strategy == unreal.PTKStrategy.FOCUSED_ASSAULT else 0.40
            check('No lane exceeds its pressure cap',
                  max(pressures) <= cap + 0.02,
                  'max {:.3f} against cap {:.2f} under {}'.format(
                      max(pressures), cap, director.get_strategy_name(plan2.strategy)))
            check('Pressure still sums to one', abs(sum(pressures) - 1.0) < 0.01,
                  round(sum(pressures), 4))
            check('Every lane keeps some chance of being used',
                  min(pressures) > 0.0,
                  round(min(pressures), 4))

            # TEST C: holding one guard should make spreading attractive. It
            # need not WIN - exploration and other signals compete - but it
            # must be a live candidate with a reason recorded.
            snap = analytics.get_snapshots()[0]
            check('Single-guard focus was seen in wave 1',
                  snap.switching.single_guard_focus
                  and str(snap.switching.focus_guard_id) == 'Wraith',
                  str(snap.switching.focus_guard_id))

            # TEST B continued: the hurt lane must be visible in the decision.
            weak = max(snap.lanes, key=lambda l: l.vulnerability)
            check('The damaged lane scored most vulnerable',
                  'Sentinel' in str(weak.base_id),
                  {str(l.lane_id): round(l.vulnerability, 2) for l in snap.lanes})
            stage = 5
            started = time.monotonic()

        # Let wave 2 run, then restart with the SAME seed and play differently.
        elif stage == 5:
            if elapsed < 8:
                return
            run_a['strategy_values'] = {
                director.get_strategy_name(s): round(director.get_strategy_value(s), 4)
                for s in [unreal.PTKStrategy.BALANCED_PRESSURE,
                          unreal.PTKStrategy.EXPLOIT_WEAK_LANE,
                          unreal.PTKStrategy.COUNTER_DOMINANT_GUARD,
                          unreal.PTKStrategy.SPLIT_PRESSURE,
                          unreal.PTKStrategy.BREAKTHROUGH,
                          unreal.PTKStrategy.FOCUSED_ASSAULT]}
            old_world = world
            unreal.GameplayStatics.get_game_mode(world).restart_run()
            stage = 6
            started = time.monotonic()

        # ---------------- RUN B: same seed, different guard ----------------
        elif stage == 6:
            fresh = editor.get_game_world()
            if fresh is None or fresh == old_world or elapsed < 4:
                return
            world = fresh
            pc = unreal.GameplayStatics.get_player_controller(world, 0)
            if not pc or not pc.get_controlled_pawn() or not actors(unreal.PTKWaveManager):
                return
            field = actors(unreal.PTKBattlefield)[0]
            waves = actors(unreal.PTKWaveManager)[0]
            director = field.get_director()
            analytics = field.get_analytics()

            check('Restart cleared the learned table',
                  all(abs(director.get_strategy_value(s) - 0.5) < 0.001 for s in [
                      unreal.PTKStrategy.BALANCED_PRESSURE,
                      unreal.PTKStrategy.EXPLOIT_WEAK_LANE,
                      unreal.PTKStrategy.SPLIT_PRESSURE]),
                  'adaptive state is per run')
            check('Restart cleared the analytics history',
                  len(analytics.get_snapshots()) == 0)
            key('Input.+key Enter')
            stage = 7
            started = time.monotonic()

        elif stage == 7:
            if elapsed < 0.8:
                return
            key('Input.-key Enter')
            check('Restart replayed the same wave seed',
                  waves.get_active_seed() == seed_a,
                  '{} vs {}'.format(seed_a, waves.get_active_seed()))
            run_b['seed'] = waves.get_active_seed()
            run_b['wave1'] = plan_summary(director.get_current_plan(), director)
            # RUN B: a different guard entirely, and a different lane hurt.
            unreal.GameplayStatics.get_player_controller(world, 0).select_guard_slot(1)
            stage = 8
            started = time.monotonic()

        elif stage == 8:
            if elapsed < 20:
                return
            hammer_lane('Wraith', 2200.0)
            clear_field()
            stage = 9
            started = time.monotonic()

        elif stage == 9:
            if waves.get_current_wave() < 2 or len(analytics.get_snapshots()) == 0:
                return
            plan2b = director.get_current_plan()
            run_b['wave2'] = plan_summary(plan2b, director)
            snap = analytics.get_snapshots()[0]
            run_b['focus'] = str(snap.switching.focus_guard_id)
            run_b['reward_wave1'] = round(director.get_last_reward(), 4)

            check('Run B focused a different guard',
                  str(snap.switching.focus_guard_id) == 'Ravager',
                  str(snap.switching.focus_guard_id))

            # THE A/B TEST. Same seed, different play - the decision must differ
            # somewhere: the strategy, what it is aimed at, or how the pressure
            # and composition are shaped.
            a2 = run_a.get('wave2', {})
            b2 = run_b.get('wave2', {})
            differences = [k for k in ('strategy', 'target_guard', 'target_lane',
                                       'pressure', 'bias')
                           if a2.get(k) != b2.get(k)]
            check('SAME SEED, different behaviour, different decision',
                  len(differences) > 0,
                  {'differs_in': differences,
                   'A': '{} -> {} / {}'.format(a2.get('strategy'), a2.get('target_guard'),
                                               a2.get('target_lane')),
                   'B': '{} -> {} / {}'.format(b2.get('strategy'), b2.get('target_guard'),
                                               b2.get('target_lane'))})

            # Fairness: the director may not have touched counts or stats.
            enemies = actors(unreal.PTKEnemyCharacter)
            if enemies:
                swarm = [e for e in enemies if str(e.get_enemy_id()) == 'SwarmNode']
                if swarm:
                    base_hp = swarm[0].get_health_component().get_max_health()
                    scale = waves.get_health_scale_for_wave(waves.get_current_wave())
                    check('Enemy health is only the wave scaling, not a secret buff',
                          abs(base_hp - 180.0 * scale) < 1.0,
                          '{:.0f} HP at wave scale x{:.2f} (expected {:.0f})'.format(
                              base_hp, scale, 180.0 * scale))
            check('Composition bias is a multiplier, not a replacement',
                  all(all(v > 0.0 for v in l.type_weights.values())
                      for l in plan2b.lanes),
                  run_b['wave2']['bias'])
            director.log_plan()
            stage = 10
            started = time.monotonic()

        # TEST D: switch constantly through wave 2, and confirm the director is
        # not told the player is camping one guard.
        elif stage == 10:
            if not analytics.is_tracking_wave():
                return
            switch_timer += delta
            if switch_timer > 1.0:
                switch_timer = 0.0
                switch_slot = switch_slot % 5 + 1
                unreal.GameplayStatics.get_player_controller(
                    world, 0).select_guard_slot(switch_slot)
            if elapsed < 26:
                return
            clear_field()
            stage = 11
            started = time.monotonic()

        elif stage == 11:
            if elapsed < 4 or len(analytics.get_snapshots()) < 2:
                return
            snap2 = analytics.get_snapshots()[1]
            check('Frequent switching is not called single-guard focus',
                  not snap2.switching.single_guard_focus,
                  '{} switches, {:.1f}/min, tempo {}, focus {}'.format(
                      snap2.switching.total_switches,
                      snap2.switching.switches_per_minute,
                      snap2.switching.tempo,
                      snap2.switching.focus_guard_id))
            check('Frequent switching reads as higher tempo',
                  snap2.switching.tempo != unreal.PTKSwitchTempo.LOW,
                  str(snap2.switching.tempo))
            run_b['wave2_switching'] = '{} switches, {:.1f}/min'.format(
                snap2.switching.total_switches, snap2.switching.switches_per_minute)
            stage = 12
            started = time.monotonic()

        elif stage == 12:
            if waves.get_current_wave() < 3:
                return
            plan3 = director.get_current_plan()
            run_b['wave3'] = plan_summary(plan3, director)
            joined = ' '.join(str(r) for r in plan3.reasoning).lower()
            check('A spread-out player is not treated as camping',
                  'held' not in joined,
                  run_b['wave3']['reasoning'])
            pressures = [l.pressure for l in plan3.lanes]
            cap = 0.55 if plan3.strategy == unreal.PTKStrategy.FOCUSED_ASSAULT else 0.40
            check('Cap still holds on the third plan',
                  max(pressures) <= cap + 0.02,
                  'max {:.3f} under {}'.format(
                      max(pressures), director.get_strategy_name(plan3.strategy)))
            run_b['strategy_values'] = {
                director.get_strategy_name(s): round(director.get_strategy_value(s), 4)
                for s in [unreal.PTKStrategy.BALANCED_PRESSURE,
                          unreal.PTKStrategy.EXPLOIT_WEAK_LANE,
                          unreal.PTKStrategy.COUNTER_DOMINANT_GUARD,
                          unreal.PTKStrategy.SPLIT_PRESSURE,
                          unreal.PTKStrategy.BREAKTHROUGH,
                          unreal.PTKStrategy.FOCUSED_ASSAULT]}
            run_b['uses'] = {
                director.get_strategy_name(s): director.get_strategy_uses(s)
                for s in [unreal.PTKStrategy.BALANCED_PRESSURE,
                          unreal.PTKStrategy.SPLIT_PRESSURE]}
            director.log_plan()
            run_b['wave3_strategy'] = director.get_strategy_name(plan3.strategy)
            run_b['wave3_value_before'] = round(
                director.get_strategy_value(plan3.strategy), 4)
            globals()['scored_strategy'] = plan3.strategy
            stage = 13
            started = time.monotonic()

        # TEST E: make wave 3 go WELL for the horde, and confirm the value of
        # the strategy that ran it climbs. Until now every reward has been low,
        # so only the falling half of the rule had actually been exercised.
        elif stage == 13:
            if elapsed < 3:
                return
            # A genuinely GOOD wave for the horde, not a mildly bad one. The
            # reward has to clear the 0.5 prior for the value to climb, and a
            # single destroyed base does not come close to that.
            for b in actors(unreal.PTKGuardBase):
                if not b.is_destroyed():
                    b.debug_apply_damage(999999.0)
            pawn = unreal.GameplayStatics.get_player_controller(world, 0).get_controlled_pawn()
            for g in actors(unreal.PTKGuardCharacter):
                if g != pawn:
                    g.get_health_component().apply_damage(999999.0, g)
            field.get_king().debug_apply_damage(1400.0)
            stage = 14
            started = time.monotonic()

        elif stage == 14:
            # Cleared every tick, not once: the wave may still be spawning, so
            # a single sweep just gets refilled and the wave never closes.
            clear_field()
            if len(analytics.get_snapshots()) < 3:
                return
            stage = 15
            started = time.monotonic()

        elif stage == 15:
            if elapsed < 1.0:
                return
            after = director.get_strategy_value(scored_strategy)
            before = run_b['wave3_value_before']
            reward = director.get_last_reward()
            run_b['wave3_reward'] = round(reward, 4)
            run_b['wave3_value_after'] = round(after, 4)

            check('A wave that went well earns a higher reward',
                  reward > run_b.get('reward_wave1', 0.0),
                  'wave 3 reward {:.3f} vs wave 1 {:.3f}'.format(
                      reward, run_b.get('reward_wave1', 0.0)))
            check('A successful strategy gains value',
                  after > before,
                  '{} {:.4f} -> {:.4f} on reward {:.3f}'.format(
                      director.get_strategy_name(scored_strategy),
                      before, after, reward))
            director.log_plan()
            stage = 16
            started = time.monotonic()

        elif stage == 16 and elapsed > 1.5:
            finish()

    except Exception:
        results['exception'] = traceback.format_exc()
        unreal.log_error(results['exception'])
        finish()


callback = unreal.register_slate_post_tick_callback(tick)
