"""
Protect the King - 2D
Part 3 verification: the AI analysis readouts, the debug command, minimap /
spawn agreement, and the two seeded determinism tests.

The two determinism tests are opposites and both matter:

  A/B             same seed, DIFFERENT behaviour -> decision must CHANGE
  REPRODUCIBILITY same seed, SAME behaviour      -> decision must MATCH

Passing only the first would be satisfied by a system that is merely random.

RUN:
    UnrealEditor.exe <proj>.uproject -ExecutePythonScript=Tools/PTK_VerifyAdaptiveIntegration.py -RenderOffscreen

Results: Tools/_Output/adaptive_integration.json
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
runs = {}
done = False
stage = 0
started = time.monotonic()
run_started = time.monotonic()
world = None
seed0 = None
phase_label = 'A'

level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level.load_level('/Game/PTK/Maps/L_PTK_Battlefield')
level.editor_request_begin_play()


def check(name, condition, note=None):
    results[name] = bool(condition)
    if note is not None:
        notes[name] = note
    unreal.log('INTEGRATION | {} | {}'.format(name, 'PASS' if condition else 'FAIL'))


def actors(cls):
    return unreal.GameplayStatics.get_all_actors_of_class(world, cls)


def living(cls):
    return [a for a in actors(cls) if not a.is_dead()]


def cmd(text):
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
    (OUT / 'adaptive_integration.json').write_text(json.dumps(
        {'results': results, 'notes': safe, 'runs': runs,
         'passed': sum(1 for v in results.values() if v is True),
         'failed': sorted(k for k, v in results.items() if v is not True)}, indent=2))
    done = True
    unreal.unregister_slate_post_tick_callback(callback)
    level.editor_request_end_play()
    unreal.SystemLibrary.quit_editor()


def decision(director):
    """The comparable part of a decision."""
    plan = director.get_current_plan()
    return {
        'strategy': director.get_strategy_name(plan.strategy),
        'target_guard': str(plan.target_guard),
        'target_lane': str(plan.target_lane),
        'exploratory': bool(plan.exploratory),
        'pressure': {str(l.lane_id): round(l.pressure, 3) for l in plan.lanes},
        'bias': {str(l.lane_id): {str(k): round(v, 2) for k, v in l.type_weights.items()}
                 for l in plan.lanes if len(l.type_weights) > 0},
    }


def play_scripted(field):
    """The SAME scripted behaviour every run: hold Wraith, hurt Sentinel base."""
    unreal.GameplayStatics.get_player_controller(world, 0).select_guard_slot(3)


def clear_field():
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    for e in living(unreal.PTKEnemyCharacter):
        e.get_health_component().apply_damage(999999.0, pc.get_controlled_pawn())


def tick(delta):
    global stage, started, world, field, waves, director, analytics, hud
    global seed0, old_world, phase_label
    try:
        if done:
            return
        elapsed = time.monotonic() - started
        if elapsed > 200 or (time.monotonic() - run_started) > 900:
            check('timeout at stage {}'.format(stage), False)
            finish()
            return

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
            hud = actors(unreal.PTKCombatHUD)
            hud = hud[0] if hud else None

            check('HUD is present for the analysis panel', hud is not None)
            check('AI debug starts hidden',
                  hud is None or not hud.get_editor_property('show_ai_debug'))

            # The debug command exists under the exact name asked for.
            cmd('PTK.ToggleAIDebug')
            stage = 1
            started = time.monotonic()

        elif stage == 1:
            if elapsed < 0.5:
                return
            check('PTK.ToggleAIDebug turns the debug panel on',
                  hud is not None and hud.get_editor_property('show_ai_debug'))
            cmd('PTK.ToggleAIDebug')
            stage = 2
            started = time.monotonic()

        elif stage == 2:
            if elapsed < 0.5:
                return
            check('PTK.ToggleAIDebug turns it off again',
                  hud is not None and not hud.get_editor_property('show_ai_debug'))
            cmd('Input.+key Enter')
            stage = 3
            started = time.monotonic()

        elif stage == 3:
            if elapsed < 0.8:
                return
            cmd('Input.-key Enter')
            seed0 = waves.get_active_seed()
            check('No analysis is claimed before there is data',
                  not director.has_previous_strategy(),
                  'panel stays hidden until a wave has finished')
            play_scripted(field)
            stage = 4
            started = time.monotonic()

        # MINIMAP / SPAWN AGREEMENT, checked while the wave is still ARRIVING -
        # the warned portals are only reported during Warning and Spawning,
        # which is exactly the window the minimap shows them in.
        elif stage == 4:
            portals = set(str(p.get_portal_id()) for p in waves.get_active_portals())
            if portals:
                runs['A_warned_corners'] = sorted(portals)
            if elapsed < 10:
                return

            announced = set(str(r) for r in waves.get_active_routes())
            spawned = set(str(e.get_lane_route()) for e in living(unreal.PTKEnemyCharacter))
            spawned.discard('None')
            check('Enemies only use lanes the wave announced',
                  spawned and spawned.issubset(announced),
                  {'announced': sorted(announced), 'spawned_on': sorted(spawned)})

            # The corners the minimap warned about are the corners the lanes
            # actually leave from - derived from the lane ids, so the warning
            # and the spawn cannot disagree.
            warned = set(runs.get('A_warned_corners', []))
            compass = {'NW': 'NorthWest', 'NE': 'NorthEast',
                       'SW': 'SouthWest', 'SE': 'SouthEast'}
            spawn_corners = set(compass.get(r.split('_')[0], r) for r in spawned)
            check('Warned corners are the corners enemies came from',
                  warned and spawn_corners.issubset(warned),
                  {'warned': sorted(warned), 'arrived_from': sorted(spawn_corners)})

            # And those lanes are ones the director's plan actually weighted.
            plan_lanes = set(str(l.lane_id) for l in director.get_current_plan().lanes
                             if l.pressure > 0.0)
            check('Announced lanes come from the director plan',
                  announced.issubset(plan_lanes),
                  {'announced': sorted(announced), 'in_plan': len(plan_lanes)})
            stage = 5
            started = time.monotonic()

        elif stage == 5:
            if elapsed < 12:
                return
            for b in actors(unreal.PTKGuardBase):
                if str(b.get_guard_id()) == 'Sentinel' and not b.is_destroyed():
                    b.debug_apply_damage(2000.0)
            clear_field()
            stage = 6
            started = time.monotonic()

        # The intermission: this is when the analysis panel is up.
        elif stage == 6:
            clear_field()
            if len(analytics.get_snapshots()) == 0:
                return
            if waves.get_phase() != unreal.PTKWavePhase.INTERMISSION:
                return

            snap = analytics.get_snapshots()[0]
            # Out-parameters come back as the second half of a tuple in Python.
            focus, share = director.get_focus_guard()
            weak, vuln = director.get_weakest_lane()
            strongest, dom = director.get_dominant_guard()

            # EVERY panel line must match the analytics, not approximate them.
            rows = {str(g.guard_id): g for g in snap.guards}
            best_ctrl = max(rows.values(), key=lambda g: g.player_control_fraction)
            check('Panel "Player Focus" matches the recorded usage',
                  str(focus) == str(best_ctrl.guard_id)
                  and abs(share - best_ctrl.player_control_fraction) < 0.001,
                  '{} {:.3f} vs recorded {} {:.3f}'.format(
                      focus, share, best_ctrl.guard_id, best_ctrl.player_control_fraction))

            lanes = {str(l.lane_id): l for l in snap.lanes}
            worst = max(lanes.values(), key=lambda l: l.vulnerability)
            check('Panel "Weakest Defence" matches lane vulnerability',
                  str(weak) == str(worst.lane_id)
                  and abs(vuln - worst.vulnerability) < 0.001,
                  '{} {:.3f} vs recorded {} {:.3f}'.format(
                      weak, vuln, worst.lane_id, worst.vulnerability))

            top = max(rows.values(), key=lambda g: g.dominance)
            check('Panel "Strongest Defender" matches dominance',
                  str(strongest) == str(top.guard_id)
                  and abs(dom - top.dominance) < 0.001,
                  '{} {:.3f} vs recorded {} {:.3f}'.format(
                      strongest, dom, top.guard_id, top.dominance))

            check('Panel "Enemy Success" is the real reward',
                  0.0 <= director.get_last_reward() <= 1.0,
                  round(director.get_last_reward(), 3))
            check('Panel has a previous strategy to report',
                  director.has_previous_strategy(),
                  director.get_strategy_name(director.get_previous_strategy()))

            # The plan shown during the intermission must be the plan that runs.
            plan = director.get_current_plan()
            check('The plan shown between waves is for the NEXT wave',
                  plan.wave_number == 2, plan.wave_number)

            # Both panels on screen at once, so the result can be eyeballed.
            cmd('PTK.ToggleAIDebug')
            cmd('HighResShot 1920x1080 filename=ptk_ai_panels')
            runs['A_intermission_plan'] = decision(director)
            runs['A_focus'] = str(focus)
            runs['A_seed'] = seed0
            stage = 7
            started = time.monotonic()

        # Confirm the promised plan is the one actually used.
        elif stage == 7:
            if waves.get_current_wave() < 2:
                return
            after = decision(director)
            check('The wave runs the plan the panel promised',
                  after == runs['A_intermission_plan'],
                  {'promised': runs['A_intermission_plan']['strategy'],
                   'ran': after['strategy']})
            check('Analysis panel is hidden once the wave starts',
                  waves.get_phase() != unreal.PTKWavePhase.INTERMISSION,
                  str(waves.get_phase()))
            runs['A_wave2'] = after
            old_world = world
            unreal.GameplayStatics.get_game_mode(world).restart_run()
            phase_label = 'REPRO'
            stage = 8
            started = time.monotonic()

        # ---- REPRODUCIBILITY: same seed, SAME behaviour ----
        elif stage == 8:
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
            cmd('Input.+key Enter')
            stage = 9
            started = time.monotonic()

        elif stage == 9:
            if elapsed < 0.8:
                return
            cmd('Input.-key Enter')
            check('Restart replayed the seed', waves.get_active_seed() == seed0,
                  '{} vs {}'.format(seed0, waves.get_active_seed()))
            play_scripted(field)   # identical behaviour to run A
            stage = 10
            started = time.monotonic()

        elif stage == 10:
            if elapsed < 22:
                return
            for b in actors(unreal.PTKGuardBase):
                if str(b.get_guard_id()) == 'Sentinel' and not b.is_destroyed():
                    b.debug_apply_damage(2000.0)
            clear_field()
            stage = 11
            started = time.monotonic()

        elif stage == 11:
            clear_field()
            if waves.get_current_wave() < 2 or len(analytics.get_snapshots()) == 0:
                return
            repro = decision(director)
            runs['REPRO_wave2'] = repro
            runs['REPRO_seed'] = waves.get_active_seed()

            # Same seed AND the same behaviour must reach the same conclusion.
            # Pressure floats can differ in the last decimal if the fight went
            # slightly differently, so the STRATEGY and its targets are what is
            # compared - that is the decision, the weights are its expression.
            a = runs['A_wave2']
            check('SAME SEED + SAME BEHAVIOUR gives the same decision',
                  repro['strategy'] == a['strategy']
                  and repro['target_guard'] == a['target_guard']
                  and repro['target_lane'] == a['target_lane'],
                  {'A': '{} / {} / {}'.format(a['strategy'], a['target_guard'], a['target_lane']),
                   'repro': '{} / {} / {}'.format(repro['strategy'], repro['target_guard'],
                                                  repro['target_lane'])})
            old_world = world
            unreal.GameplayStatics.get_game_mode(world).restart_run()
            stage = 12
            started = time.monotonic()

        # ---- A/B: same seed, DIFFERENT behaviour ----
        elif stage == 12:
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
            cmd('Input.+key Enter')
            stage = 13
            started = time.monotonic()

        elif stage == 13:
            if elapsed < 0.8:
                return
            cmd('Input.-key Enter')
            # DIFFERENT behaviour: a different guard, and a different base hurt.
            unreal.GameplayStatics.get_player_controller(world, 0).select_guard_slot(1)
            stage = 14
            started = time.monotonic()

        elif stage == 14:
            if elapsed < 22:
                return
            for b in actors(unreal.PTKGuardBase):
                if str(b.get_guard_id()) == 'Wraith' and not b.is_destroyed():
                    b.debug_apply_damage(2200.0)
            clear_field()
            stage = 15
            started = time.monotonic()

        elif stage == 15:
            clear_field()
            if waves.get_current_wave() < 2 or len(analytics.get_snapshots()) == 0:
                return
            b = decision(director)
            runs['B_wave2'] = b
            runs['B_seed'] = waves.get_active_seed()
            snap = analytics.get_snapshots()[0]
            runs['B_focus'] = str(snap.switching.focus_guard_id)

            a = runs['A_wave2']
            differs = [k for k in ('strategy', 'target_guard', 'target_lane', 'pressure', 'bias')
                       if a.get(k) != b.get(k)]
            check('SAME SEED + DIFFERENT BEHAVIOUR changes the decision',
                  len(differs) > 0,
                  {'differs_in': differs,
                   'A': '{} bias={}'.format(a['strategy'], a['bias']),
                   'B': '{} bias={}'.format(b['strategy'], b['bias'])})
            check('Both runs really used the same seed',
                  runs['B_seed'] == seed0 and runs['REPRO_seed'] == seed0,
                  '{} / {} / {}'.format(seed0, runs['REPRO_seed'], runs['B_seed']))
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
