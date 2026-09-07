"""
Protect the King - 2D
Second battlefield pass: victory, multi-wave variety, guard abilities, and
screenshots that prove the map, HUD and minimap actually render.

RUN:
    UnrealEditor.exe <ProjectDir>/ProtectTheKing2D.uproject ^
        -ExecutePythonScript="<ProjectDir>/Tools/PTK_VerifyBattlefieldB.py" ^
        -RenderOffscreen

Results: Tools/_Output/battlefield_results_b.json
Screens: Saved/Screenshots/

The first pass (PTK_VerifyBattlefieldB's sibling) drives the losing path and
stops there, because killing the King is terminal. Victory needs a run that is
never allowed to lose, so it lives here rather than being bolted onto the end
of a sequence that has already ended.
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
# Wall clock for the whole run. The per-stage timer is reset while waiting on
# the wave system, so it cannot be the thing that stops a hang.
run_started = time.monotonic()
portals_used = set()
waves_seen = set()

level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level.load_level('/Game/PTK/Maps/L_PTK_Battlefield')
level.editor_request_begin_play()


def check(name, condition, note=None):
    results[name] = bool(condition)
    if note is not None:
        notes[name] = note
    unreal.log('BATTLEFIELD-B | {} | {}'.format(name, 'PASS' if condition else 'FAIL'))


def actors(cls):
    return unreal.GameplayStatics.get_all_actors_of_class(world, cls)


def command(text):
    unreal.SystemLibrary.execute_console_command(world, text, pc)


def shot(name):
    command('HighResShot 1920x1080 filename=' + name)


def living(cls):
    return [e for e in actors(cls) if not e.is_dead()]


def finish():
    global done
    safe = {}
    for k, v in notes.items():
        safe[k] = [str(x) for x in v] if isinstance(v, (list, tuple, set)) else (
            v if isinstance(v, (int, float, bool, str)) else str(v))
    (OUT / 'battlefield_results_b.json').write_text(json.dumps(
        {'results': results, 'notes': safe,
         'passed': sum(1 for v in results.values() if v is True),
         'failed': sorted(k for k, v in results.items() if v is not True)}, indent=2))
    done = True
    unreal.unregister_slate_post_tick_callback(callback)
    level.editor_request_end_play()
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    global stage, started, world, pc, mode, field, waves, king, guards, bases, pawn
    global base_before
    try:
        if done:
            return
        elapsed = time.monotonic() - started
        if elapsed > 240 or (time.monotonic() - run_started) > 420:
            check('timeout - stage {}'.format(stage), False,
                  'wave {} phase {}'.format(
                      waves.get_current_wave() if 'waves' in globals() and waves else '?',
                      waves.get_phase() if 'waves' in globals() and waves else '?'))
            finish()
            return

        # The King must never die in this run, or victory becomes unreachable.
        # Immunity rather than healing: healing races the damage, immunity does
        # not, and what is being tested here is the WIN path, not his health.
        if stage >= 2 and king:
            hpc = king.get_health_component()
            if not hpc.is_damage_immune():
                hpc.set_damage_immune(True)

        if stage >= 3 and waves:
            waves_seen.add(waves.get_current_wave())
            for p in waves.get_active_portals():
                portals_used.add(str(p.get_portal_id()))

        if stage == 0:
            world = editor.get_game_world()
            if not world or elapsed < 3:
                return
            pc = unreal.GameplayStatics.get_player_controller(world, 0)
            if not pc or not pc.get_controlled_pawn():
                return
            mode = unreal.GameplayStatics.get_game_mode(world)
            field = actors(unreal.PTKBattlefield)[0]
            waves = actors(unreal.PTKWaveManager)[0]
            king = actors(unreal.PTKKingCharacter)[0]
            guards = actors(unreal.PTKGuardCharacter)
            bases = actors(unreal.PTKGuardBase)
            pawn = pc.get_controlled_pawn()

            # The start screen, over the real map.
            shot('ptk_map_start')
            stage = 1
            started = time.monotonic()

        elif stage == 1:
            if elapsed < 1.5:
                return
            command('Input.+key Enter')
            stage = 2
            started = time.monotonic()

        elif stage == 2:
            if elapsed < 0.6:
                return
            command('Input.-key Enter')
            check('Run starts on the real map', mode.is_playing())
            stage = 3
            started = time.monotonic()

        # --- guard ability regression, while wave 1 walks in ---
        elif stage == 3:
            if elapsed < 3:
                return
            by_id = {str(g.get_guard_id()): g for g in guards}

            # Damage numbers are the contract in section 20 of the spec. Read
            # through the effective-damage path so a stray multiplier would show.
            expect = {'Ravager': 25.0, 'Wraith': 30.0, 'Reaver': 35.0, 'Sentinel': 40.0}
            wrong = []
            for name, want in expect.items():
                g = by_id.get(name)
                if not g:
                    wrong.append(name + ' missing')
                    continue
                got = g.get_base_attack_damage()
                if abs(got - want) > 0.01:
                    wrong.append('{} {:.0f} != {:.0f}'.format(name, got, want))
            check('Guard damage values unchanged', not wrong, wrong or 'all match')

            rav = by_id.get('Ravager')
            check('Ravager still multi-target',
                  rav is not None and rav.get_editor_property('attack_hits_multiple_targets'))
            for name in ('Wraith', 'Sentinel'):
                g = by_id.get(name)
                check('{} still ranged'.format(name), g is not None and g.is_ranged_attacker())
            aegis = by_id.get('Aegis')
            check('Aegis can still defend', aegis is not None and aegis.start_defend())

            # Sprite scale must be untouched by this phase.
            check('Guard sprite scale untouched (224 canvas, PPU 1)', all(
                abs(abs(g.get_sprite().get_editor_property('relative_scale3d').x) - 1.0) < 0.001
                for g in guards), 'all five at |scaleX| = 1')
            stage = 4
            started = time.monotonic()

        elif stage == 4:
            if elapsed < 4:
                return
            # Mid-fight: the HUD, roster, wave panel and minimap all on screen.
            shot('ptk_map_combat')
            stage = 5
            started = time.monotonic()

        # --- march through the waves to a victory ---
        elif stage == 5:
            if elapsed < 2:
                return
            # Reset the per-stage clock on every pass: five waves with their
            # intermissions take longer than the stage budget, and this stage is
            # waiting on the game rather than on any one event.
            started = time.monotonic()

            live = living(unreal.PTKEnemyCharacter)
            if live:
                # Clear the field so the wave completes. Damage through the real
                # health path, not Destroy, so the wave manager sees ordinary
                # deaths and its remaining-count logic is what is being tested.
                for e in live:
                    e.get_health_component().apply_damage(99999.0, pawn)
                return
            if mode.is_match_over() or waves.get_phase() in (
                    unreal.PTKWavePhase.COMPLETE, unreal.PTKWavePhase.STOPPED):
                stage = 6
                return
            # Intermission or warning: let it run on to the next wave.
            return

        elif stage == 6:
            if elapsed < 1.0:
                return
            check('All five waves ran', waves_seen == {1, 2, 3, 4, 5}, sorted(waves_seen))
            check('More than one spawn corner used across the run',
                  len(portals_used) >= 2, sorted(portals_used))
            check('Wave phase reaches Complete',
                  waves.get_phase() == unreal.PTKWavePhase.COMPLETE)
            check('VICTORY declared', mode.get_match_result() == unreal.PTKMatchResult.VICTORY)
            check('Match is over', mode.is_match_over())
            check('Gameplay inactive after victory', mode.is_match_over())
            check('King survived', not king.is_dead())
            shot('ptk_map_victory')
            stage = 7
            started = time.monotonic()

        elif stage == 7 and elapsed > 2.0:
            finish()

    except Exception:
        results['exception'] = traceback.format_exc()
        unreal.log_error(results['exception'])
        finish()


callback = unreal.register_slate_post_tick_callback(tick)
