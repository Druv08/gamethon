"""Run with UnrealEditor -ExecutePythonScript=<this file> -RenderOffscreen.

Exercises mapped keys through Enhanced Input console injection and records results in Tools/_Output.
Uses normal PIE, not SIE. Does not save or modify level/assets.
Offscreen rendering isolates the test from desktop input; physical focus is manual.
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
enemy_damage_seen = False
stage = 0
started = time.monotonic()
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level.load_level('/Game/PTK/Maps/L_PTK_TestGround')
level.editor_request_begin_play()


def check(name, condition):
    results[name] = bool(condition)
    unreal.log('START TEST | {} | {}'.format(name, 'PASS' if condition else 'FAIL'))


def actors(cls):
    return unreal.GameplayStatics.get_all_actors_of_class(world, cls)


def command(text):
    unreal.SystemLibrary.execute_console_command(world, text, pc)


def inject(key):
    command('Input.+key ' + key)


def release(*keys):
    for key in keys:
        command('Input.-key ' + key)


def widgets():
    return unreal.WidgetLibrary.get_all_widgets_of_class(world, unreal.PTKStartScreen, True)


def finish():
    (OUT / 'start_screen_results.json').write_text(json.dumps(results, indent=2))
    unreal.unregister_slate_post_tick_callback(callback)
    level.editor_request_end_play()
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    global stage, started, world, pc, mode, guards, positions, pawn, enemy_damage_seen
    global start_action, move_action, attack_action, switch_action, enemies, before_move
    try:
        elapsed = time.monotonic() - started
        if stage >= 3:
            enemy_damage_seen = enemy_damage_seen or any(
                e.get_health_component().get_current_health() < e.get_health_component().get_max_health()
                for e in actors(unreal.PTKEnemyCharacter))
        if elapsed > 90:
            check('timeout', False)
            finish()
            return
        if stage == 0:
            world = editor.get_game_world()
            if not world or elapsed < 3:
                return
            pc = unreal.GameplayStatics.get_player_controller(world, 0)
            if not pc or not pc.get_controlled_pawn():
                return
            mode = unreal.GameplayStatics.get_game_mode(world)
            guards = actors(unreal.PTKGuardCharacter)
            pawn = pc.get_controlled_pawn()
            positions = [g.get_actor_location() for g in guards]
            check('WaitingToStart', not mode.is_playing())
            check('Five guards and King visible', len(guards) == 5 and len(actors(unreal.PTKKingCharacter)) == 1
                  and all(not g.get_editor_property('hidden') for g in guards + actors(unreal.PTKKingCharacter)))
            check('Camera valid', pc.get_view_target() == pawn)
            screens = widgets()
            widget = screens[0] if screens else None
            check('START SCREEN', widget is not None and widget.is_in_viewport())
            check('NO ENEMIES BEFORE ENTER', len(actors(unreal.PTKEnemyCharacter)) == 0)
            for spawner in actors(unreal.PTKEnemySpawner):
                check('Spawner refuses before start', spawner.spawn_wave() == 0)
            start_action = 'Enter'
            move_action = 'D'
            attack_action = 'LeftMouseButton'
            switch_action = 'Two'
            check('Attack and defend refused', all(not g.start_attack() and not g.start_defend() for g in guards))
            check('Switch refused', not pc.select_guard_slot(2) and pc.get_controlled_pawn() == pawn)
            command('Shot showui')
            stage = 1
            started = time.monotonic()
        elif stage == 1:
            inject(move_action)
            inject(attack_action)
            inject(switch_action)
            if elapsed < 2:
                return
            check('PLAYER LOCKED BEFORE ENTER', pc.get_controlled_pawn() == pawn and
                  all((g.get_actor_location() - pos).length() < 0.1 and not g.is_attacking()
                      for g, pos in zip(guards, positions)))
            check('GUARD AI LOCKED BEFORE ENTER', all(
                g.get_controller().get_target() is None for g in guards if g != pawn))
            check('Still zero enemies', len(actors(unreal.PTKEnemyCharacter)) == 0)
            release(move_action, attack_action, switch_action)
            stage = 2
            started = time.monotonic()
        elif stage == 2:
            if elapsed < 0.5:
                return
            inject(start_action)
            stage = 3
            started = time.monotonic()
        elif stage == 3:
            if elapsed < 0.5:
                return
            check('ENTER START', mode.is_playing() and not widgets())
            release(start_action)
            enemies = actors(unreal.PTKEnemyCharacter)
            check('ENEMIES SPAWN AFTER ENTER', len(enemies) > 0)
            before_move = pawn.get_actor_location()
            stage = 4
            started = time.monotonic()
        elif stage == 4:
            inject(move_action)
            if elapsed < 1:
                return
            check('PLAYER INPUT AFTER ENTER', (pawn.get_actor_location() - before_move).length() > 1)
            release(move_action)
            inject(attack_action)
            stage = 5
            started = time.monotonic()
        elif stage == 5:
            # Polled, not timed. This harness renders offscreen and ticks at
            # roughly 3 Hz, so a fixed 0.05 s window is frequently LESS than a
            # single game frame and the injected key has not been processed
            # yet - the check was racing the frame rate, not the feature.
            if not pawn.is_attacking() and elapsed < 4.0:
                return
            check('Player attack after start', pawn.is_attacking())
            release(attack_action)
            inject(switch_action)
            stage = 6
            started = time.monotonic()
        elif stage == 6:
            slot2 = pc.get_guard_in_slot(2)
            if pc.get_controlled_pawn() != slot2 and elapsed < 4.0:
                return
            check('GUARD SWITCHING AFTER ENTER', pc.get_controlled_pawn() == slot2)
            release(switch_action)
            inject(start_action)
            stage = 7
            started = time.monotonic()
        elif stage == 7:
            if elapsed < 0.3:
                return
            check('Enter cannot start twice', all(e in enemies for e in actors(unreal.PTKEnemyCharacter)))
            release(start_action)
            pc.select_guard_slot(1)
            stage = 8
            started = time.monotonic()
        elif stage == 8:
            if elapsed < 10:
                return
            check('NORMAL COMBAT AFTER ENTER', enemy_damage_seen)
            check('Enemies attack guards', any(
                g.get_health_component().get_current_health() < g.get_health_component().get_max_health()
                for g in guards))
            command('Shot showui')
            stage = 9
            started = time.monotonic()
        elif stage == 9 and elapsed > 1:
            finish()
    except Exception:
        results['exception'] = traceback.format_exc()
        unreal.log_error(results['exception'])
        finish()


callback = unreal.register_slate_post_tick_callback(tick)
