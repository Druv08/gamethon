"""PIE regression for AI ranged aiming. Changes transient test state only.

Run with UnrealEditor -ExecutePythonScript=<this file> -RenderOffscreen -unattended.
Results: Tools/_Output/guard_aim_results.json.
"""
import json
import time
import traceback
from pathlib import Path
import unreal

OUT = Path(unreal.Paths.project_dir()) / 'Tools/_Output'
OUT.mkdir(parents=True, exist_ok=True)
results = {}
world = None
moving = None
deadline = 0.0
started = time.monotonic()
enemy_class = unreal.EditorAssetLibrary.load_asset(
    '/Game/PTK/Characters/Enemies/SwarmNode/Blueprints/BP_SwarmNode').generated_class()
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
level.load_level('/Game/PTK/Maps/L_PTK_TestGround')
level.editor_request_begin_play()


def actors(cls):
    return unreal.GameplayStatics.get_all_actors_of_class(world, cls)


def check(name, ok):
    results[name] = bool(ok)
    unreal.log('GUARD AIM | {} | {}'.format(name, 'PASS' if ok else 'FAIL'))


def move(actor, position):
    actor.set_actor_location(position, False, True)


def clear_shots():
    for shot in actors(unreal.PTKProjectile):
        shot.destroy_actor()


def run():
    global world, moving
    while not editor.get_game_world():
        yield 0.2
    world = editor.get_game_world()
    yield 2.0
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    unreal.GameplayStatics.get_game_mode(world).start_game()
    spawner = actors(unreal.PTKEnemySpawner)[0]
    spawner.clear_wave()
    guards = actors(unreal.PTKGuardCharacter)
    for index, guard in enumerate(guards):
        if guard.get_controller() != pc:
            guard.get_controller().set_actor_tick_enabled(False)
        guard.set_actor_tick_enabled(False)
        guard.get_component_by_class(unreal.CharacterMovementComponent).set_component_tick_enabled(False)
        move(guard, unreal.Vector(3000 + index * 1000, 0, 0))
    entry = unreal.PTKEnemySpawnEntry()
    entry.set_editor_property('enemy_class', enemy_class)
    entry.set_editor_property('count', 1)
    spawner.set_editor_property('spawn_count', 0)
    spawner.set_editor_property('additional_enemies', [entry])

    for name, slot in [('Wraith', 3), ('Sentinel', 5)]:
        guard = pc.get_guard_in_slot(slot)
        ai = guard.get_controller()
        move(guard, unreal.Vector(0, 0, 0))
        guard.set_home_position(unreal.Vector(0, 0, 0))
        guard.set_actor_tick_enabled(True)
        for scenario in ['diagonal', 'moves_during_windup', 'crossing', 'dead_before_release']:
            clear_shots()
            spawner.clear_wave()
            spawner.spawn_wave()
            enemy = actors(unreal.PTKEnemyCharacter)[0]
            enemy.set_actor_tick_enabled(False)
            enemy.get_controller().set_actor_tick_enabled(False)
            movement = enemy.get_component_by_class(unreal.CharacterMovementComponent)
            movement.stop_movement_immediately()
            movement.set_component_tick_enabled(False)
            move(enemy, unreal.Vector(220, 0, 120))
            enemy.get_health_component().set_max_health(1000)
            before = enemy.get_health_component().get_current_health()
            ai.set_actor_tick_enabled(True)
            until = time.monotonic() + 2
            while not guard.is_attacking() and time.monotonic() < until:
                yield 0.01
            check(name + '_' + scenario + '_acquires_target', ai.get_target() == enemy and guard.is_attacking())
            # Finish this one attack without starting another or retargeting.
            ai.set_actor_tick_enabled(False)
            if scenario == 'moves_during_windup':
                move(enemy, unreal.Vector(200, 0, -140))
            elif scenario == 'crossing':
                move(enemy, unreal.Vector(220, 0, -100))
                movement.set_component_tick_enabled(True)
                moving = enemy
            elif scenario == 'dead_before_release':
                enemy.get_health_component().apply_damage(999999, guard)
            yield 0.5
            if scenario == 'dead_before_release':
                check(name + '_dead_target_does_not_fire', not actors(unreal.PTKProjectile))
            yield 0.45
            if scenario != 'dead_before_release':
                check(name + '_' + scenario + '_hits_selected_enemy',
                      enemy.get_health_component().get_current_health() < before)
            moving = None
            movement.stop_movement_immediately()
            movement.set_component_tick_enabled(False)
            yield 0.5

        # Taking control must restore the existing directional player attack.
        clear_shots()
        spawner.clear_wave()
        check(name + '_player_takeover', pc.select_guard_slot(slot))
        guard.set_facing_direction(unreal.PTKFacingDirection.LEFT)
        check(name + '_player_can_fire_without_ai_target', guard.start_attack())
        until = time.monotonic() + 1.0
        while not actors(unreal.PTKProjectile) and time.monotonic() < until:
            yield 0.01
        shots = actors(unreal.PTKProjectile)
        check(name + '_player_shot_keeps_cardinal_direction', bool(shots) and all(
            abs(s.get_actor_location().z - guard.get_actor_location().z) < 1 for s in shots))
        yield 0.6
        pc.select_guard_slot(1)
        guard.get_controller().set_actor_tick_enabled(False)
        guard.set_actor_tick_enabled(False)
        move(guard, unreal.Vector(5000, 0, 0))


def finish():
    (OUT / 'guard_aim_results.json').write_text(json.dumps(results, indent=2))
    unreal.unregister_slate_post_tick_callback(callback)
    level.editor_request_end_play()
    unreal.SystemLibrary.quit_editor()


sequence = run()


def tick(delta):
    global deadline
    try:
        if moving:
            moving.add_movement_input(unreal.Vector(0, 0, 1), 1.0, True)
        if time.monotonic() - started > 100:
            raise RuntimeError('Guard aim test timed out')
        if time.monotonic() < deadline:
            return
        deadline = time.monotonic() + next(sequence)
    except StopIteration:
        finish()
    except Exception:
        results['exception'] = traceback.format_exc()
        unreal.log_error(results['exception'])
        finish()


callback = unreal.register_slate_post_tick_callback(tick)
