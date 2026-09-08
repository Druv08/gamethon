"""
Protect the King - 2D
Verifies RESTART and NEW GAME fully reset a run.

Deliberately makes a MESS first - dead guards, a destroyed base, a spent King
power, a later wave, enemies on the field - so the reset has something real to
undo. A reset tested from a clean start proves nothing.

RUN:
    UnrealEditor.exe <proj>.uproject -ExecutePythonScript=Tools/PTK_VerifyRestart.py -RenderOffscreen

Results: Tools/_Output/restart_results.json
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
first_seed = None
restart_seed = None

level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level.load_level('/Game/PTK/Maps/L_PTK_Battlefield')
level.editor_request_begin_play()


def check(name, condition, note=None):
    results[name] = bool(condition)
    if note is not None:
        notes[name] = note
    unreal.log('RESET | {} | {}'.format(name, 'PASS' if condition else 'FAIL'))


def actors(cls):
    return unreal.GameplayStatics.get_all_actors_of_class(world, cls)


def living(cls):
    return [a for a in actors(cls) if not a.is_dead()]


def finish():
    global done
    safe = {}
    for k, v in notes.items():
        safe[k] = v if isinstance(v, (int, float, bool, str)) else str(v)
    (OUT / 'restart_results.json').write_text(json.dumps(
        {'results': results, 'notes': safe,
         'passed': sum(1 for v in results.values() if v is True),
         'failed': sorted(k for k, v in results.items() if v is not True)}, indent=2))
    done = True
    unreal.unregister_slate_post_tick_callback(callback)
    level.editor_request_end_play()
    unreal.SystemLibrary.quit_editor()


def snapshot_clean(label):
    """Every condition a freshly reset run must satisfy."""
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    mode = unreal.GameplayStatics.get_game_mode(world)
    field = actors(unreal.PTKBattlefield)[0]
    waves = actors(unreal.PTKWaveManager)[0]
    king = field.get_king()
    guards = actors(unreal.PTKGuardCharacter)
    bases = actors(unreal.PTKGuardBase)
    enemies = actors(unreal.PTKEnemyCharacter)

    kh = king.get_health_component()
    check(label + ': King back to full health',
          abs(kh.get_current_health() - kh.get_max_health()) < 0.5,
          '{:.0f}/{:.0f}'.format(kh.get_current_health(), kh.get_max_health()))

    check(label + ': all five guards alive and whole',
          len(guards) == 5 and all(
              not g.is_dead()
              and abs(g.get_health_component().get_current_health()
                      - g.get_health_component().get_max_health()) < 0.5
              for g in guards),
          '{} guards, {} at full'.format(
              len(guards),
              sum(1 for g in guards
                  if not g.is_dead()
                  and abs(g.get_health_component().get_current_health()
                          - g.get_health_component().get_max_health()) < 0.5)))

    check(label + ': all five bases intact at full health',
          len(bases) == 5 and all(
              not b.is_destroyed()
              and abs(b.get_health_component().get_current_health() - 2500.0) < 0.5
              for b in bases),
          '{} bases, {} destroyed'.format(
              len(bases), sum(1 for b in bases if b.is_destroyed())))

    check(label + ': ruins hidden again',
          all(b.get_editor_property('ruins_sprite') is None
              or not b.get_editor_property('ruins_sprite').get_editor_property('visible')
              for b in bases))

    check(label + ': no enemies before Enter', len(enemies) == 0, len(enemies))
    check(label + ': wave system back to the start',
          waves.get_current_wave() <= 1 and not waves.is_run_complete(),
          'wave {} phase {}'.format(waves.get_current_wave(), waves.get_phase()))
    check(label + ': match is not over', not mode.is_match_over())
    check(label + ': waiting for Enter again', not mode.is_playing())

    check(label + ': King power ready again',
          king.can_activate_power() and king.get_power_cooldown_remaining() <= 0.0
          and king.get_boosted_guard() is None,
          'cooldown {:.0f}s'.format(king.get_power_cooldown_remaining()))

    pawn = pc.get_controlled_pawn()
    check(label + ': player is driving Ravager again',
          pawn is not None and str(pawn.get_guard_id()) == 'Ravager',
          str(pawn.get_guard_id()) if pawn else 'no pawn')

    ai = [g for g in guards
          if g != pawn and isinstance(g.get_controller(), unreal.PTKGuardAIController)]
    check(label + ': the other four are back on AI', len(ai) == 4, len(ai))

    check(label + ': guards standing on their own posts',
          all((g.get_actor_location() - g.get_home_position()).length() < 90.0
              for g in guards),
          max((g.get_actor_location() - g.get_home_position()).length()
              for g in guards))

    # Nothing duplicated by the reload.
    check(label + ': no duplicated actors',
          len(guards) == 5 and len(bases) == 5
          and len(actors(unreal.PTKBattlefield)) == 1
          and len(actors(unreal.PTKWaveManager)) == 1
          and len(actors(unreal.PTKKingCharacter)) == 1,
          '{} field / {} waves / {} kings'.format(
              len(actors(unreal.PTKBattlefield)),
              len(actors(unreal.PTKWaveManager)),
              len(actors(unreal.PTKKingCharacter))))
    return waves.get_active_seed()


def make_a_mess():
    """Damage everything a run can damage, so the reset has work to do."""
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    field = actors(unreal.PTKBattlefield)[0]
    king = field.get_king()
    guards = actors(unreal.PTKGuardCharacter)
    bases = actors(unreal.PTKGuardBase)

    king.debug_apply_damage(king.get_health_component().get_max_health() * 0.7)
    bases[0].debug_apply_damage(999999.0)
    bases[1].debug_apply_damage(600.0)
    for g in guards:
        if g != pc.get_controlled_pawn():
            g.get_health_component().apply_damage(400.0, king)
            break
    pc.select_guard_slot(3)


def tick(delta):
    global stage, started, world, first_seed, restart_seed, old_world
    try:
        if done:
            return
        elapsed = time.monotonic() - started
        if elapsed > 120 or (time.monotonic() - run_started) > 500:
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
            unreal.SystemLibrary.execute_console_command(world, 'Input.+key Enter', pc)
            stage = 1
            started = time.monotonic()

        elif stage == 1:
            if elapsed < 0.6:
                return
            pc = unreal.GameplayStatics.get_player_controller(world, 0)
            unreal.SystemLibrary.execute_console_command(world, 'Input.-key Enter', pc)
            stage = 2
            started = time.monotonic()

        # Let a real fight happen, then wreck things.
        elif stage == 2:
            if elapsed < 14:
                return
            waves = actors(unreal.PTKWaveManager)[0]
            first_seed = waves.get_active_seed()
            make_a_mess()
            stage = 3
            started = time.monotonic()

        elif stage == 3:
            if elapsed < 1.5:
                return
            field = actors(unreal.PTKBattlefield)[0]
            king = field.get_king()
            bases = actors(unreal.PTKGuardBase)
            check('Setup: the run really is in a mess',
                  king.get_health_component().get_health_fraction() < 0.5
                  and any(b.is_destroyed() for b in bases)
                  and len(actors(unreal.PTKEnemyCharacter)) > 0,
                  'King {:.0f}%, {} base(s) destroyed, {} enemies'.format(
                      king.get_health_component().get_health_fraction() * 100.0,
                      sum(1 for b in bases if b.is_destroyed()),
                      len(actors(unreal.PTKEnemyCharacter))))

            old_world = world
            mode = unreal.GameplayStatics.get_game_mode(world)
            mode.restart_run()
            stage = 4
            started = time.monotonic()

        # Wait for the reloaded world to come up.
        elif stage == 4:
            fresh = editor.get_game_world()
            if fresh is None or fresh == old_world or elapsed < 4:
                return
            world = fresh
            pc = unreal.GameplayStatics.get_player_controller(world, 0)
            if not pc or not pc.get_controlled_pawn():
                return
            if not actors(unreal.PTKWaveManager):
                return
            restart_seed = snapshot_clean('RESTART')
            check('RESTART replays the same wave seed',
                  restart_seed == first_seed and first_seed not in (None, 0),
                  '{} -> {}'.format(first_seed, restart_seed))
            stage = 5
            started = time.monotonic()

        # Confirm the reset run is actually playable, then try NEW GAME.
        elif stage == 5:
            if elapsed < 1.0:
                return
            pc = unreal.GameplayStatics.get_player_controller(world, 0)
            unreal.SystemLibrary.execute_console_command(world, 'Input.+key Enter', pc)
            stage = 6
            started = time.monotonic()

        elif stage == 6:
            if elapsed < 6:
                return
            pc = unreal.GameplayStatics.get_player_controller(world, 0)
            unreal.SystemLibrary.execute_console_command(world, 'Input.-key Enter', pc)
            mode = unreal.GameplayStatics.get_game_mode(world)
            check('RESTART: Enter still starts a normal run',
                  mode.is_playing() and len(actors(unreal.PTKEnemyCharacter)) > 0,
                  '{} enemies'.format(len(actors(unreal.PTKEnemyCharacter))))

            make_a_mess()
            old_world = world
            mode.new_game_run()
            stage = 7
            started = time.monotonic()

        elif stage == 7:
            fresh = editor.get_game_world()
            if fresh is None or fresh == old_world or elapsed < 4:
                return
            world = fresh
            pc = unreal.GameplayStatics.get_player_controller(world, 0)
            if not pc or not pc.get_controlled_pawn():
                return
            if not actors(unreal.PTKWaveManager):
                return
            new_seed = snapshot_clean('NEW GAME')
            check('NEW GAME randomises afresh',
                  new_seed not in (0, None) and new_seed != restart_seed,
                  '{} (was {})'.format(new_seed, restart_seed))
            stage = 8
            started = time.monotonic()

        elif stage == 8 and elapsed > 1.0:
            finish()

    except Exception:
        results['exception'] = traceback.format_exc()
        unreal.log_error(results['exception'])
        finish()


callback = unreal.register_slate_post_tick_callback(tick)
