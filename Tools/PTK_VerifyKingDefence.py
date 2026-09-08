"""Real battlefield PIE regression for emergency defence and overhead health bars.

Run with -ExecutePythonScript=<this file> -RenderOffscreen -unattended.
Only transient test state changes; no maps or assets are saved.
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
deadline = 0.0
started = time.monotonic()
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
level.load_level('/Game/PTK/Maps/L_PTK_Battlefield')
level.editor_request_begin_play()


def actors(cls):
    return unreal.GameplayStatics.get_all_actors_of_class(world, cls)


def check(label, ok):
    results[label] = bool(ok)
    unreal.log('KING DEFENCE | {} | {}'.format(label, 'PASS' if ok else 'FAIL'))


def move(actor, position):
    actor.set_actor_location(position, False, True)


def run():
    global world
    while not editor.get_game_world():
        yield 0.2
    world = editor.get_game_world()
    yield 2.0
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    king = actors(unreal.PTKKingCharacter)[0]
    waves = actors(unreal.PTKWaveManager)[0]
    guards = [g for g in actors(unreal.PTKGuardCharacter) if g != pc.get_controlled_pawn()]
    player = pc.get_controlled_pawn()
    for g in guards:
        g.get_controller().set_actor_tick_enabled(False)
    unreal.GameplayStatics.get_game_mode(world).start_game()
    while not actors(unreal.PTKEnemyCharacter):
        yield 0.1
    waves.stop_run()
    enemies = actors(unreal.PTKEnemyCharacter)
    enemy = enemies[0]
    for extra in enemies[1:]:
        extra.destroy_actor()
    core = king.get_actor_location()
    move(player, core + unreal.Vector(1800, 0, 0))
    positions = [(1000, 0), (-1000, 0), (0, 1000), (0, -1000)]
    homes = {}
    for g, (x, z) in zip(guards, positions):
        home = core + unreal.Vector(x, 0, z)
        move(g, home)
        g.set_home_position(home)
        homes[str(g.get_guard_id())] = home
    guards[0].get_health_component().apply_damage(
        guards[0].get_health_component().get_current_health() * 0.8, king)
    move(enemy, core + unreal.Vector(35, 0, 0))
    enemy.get_health_component().set_max_health(10000)
    enemy.set_editor_property('attack_damage', 1.0)
    king.get_health_component().set_damage_immune(True)
    yield 0.5
    check('Single enemy targets King', enemy.get_target() == king)
    for g in guards:
        g.get_controller().set_actor_tick_enabled(True)
    yield 0.5
    for g in guards:
        name = str(g.get_guard_id())
        check(name + ' prioritises King outside home leash', g.get_controller().get_target() == enemy)
        check(name + ' moves towards King',
              (g.get_actor_location() - core).length() < (homes[name] - core).length() - 30)
    check('All four respond despite ordinary two-helper limit',
          all(g.get_controller().get_assist_target() == king for g in guards))
    yield 8.0
    check('Guards reach and damage the King attacker',
          enemy.get_health_component().get_current_health() < 10000)
    check('Player possession unchanged', pc.get_controlled_pawn() == player)

    # Isolate a visible enemy for screenshot inspection and anchoring checks.
    for g in guards:
        g.get_controller().set_actor_tick_enabled(False)
    enemy.set_actor_tick_enabled(False)
    enemy.get_component_by_class(unreal.CharacterMovementComponent).stop_movement_immediately()
    enemy.get_component_by_class(unreal.CharacterMovementComponent).set_component_tick_enabled(False)
    move(player, core + unreal.Vector(0, 0, -250))
    move(enemy, core + unreal.Vector(250, 0, -150))
    yield 0.3
    anchor = enemy.get_health_bar_anchor()
    check('Enemy head anchor above and centred on actor',
          abs(anchor.x - enemy.get_actor_location().x) < 1 and anchor.z > enemy.get_actor_location().z + 30)
    unreal.SystemLibrary.execute_console_command(world, 'HighResShot 1920x1080 filename=ptk_enemy_bar_before', pc)
    yield 1.0
    move(enemy, enemy.get_actor_location() + unreal.Vector(-200, 0, 200))
    yield 0.2
    delta = enemy.get_health_bar_anchor() - anchor
    check('Head anchor tracks both movement axes exactly', abs(delta.x + 200) < 1 and abs(delta.z - 200) < 1)
    unreal.SystemLibrary.execute_console_command(world, 'HighResShot 1920x1080 filename=ptk_enemy_bar_after', pc)
    yield 1.0

    enemy.destroy_actor()
    for shot in actors(unreal.PTKProjectile):
        shot.destroy_actor()
    for g in guards:
        g.get_controller().set_actor_tick_enabled(True)
    yield 10.0
    for g in guards:
        check(str(g.get_guard_id()) + ' returns home when King is safe',
              (g.get_actor_location() - g.get_home_position()).length() < 80)


def finish():
    (OUT / 'king_defence_results.json').write_text(json.dumps(results, indent=2))
    unreal.unregister_slate_post_tick_callback(callback)
    level.editor_request_end_play()
    unreal.SystemLibrary.quit_editor()


sequence = run()


def tick(delta):
    global deadline
    try:
        if time.monotonic() - started > 100:
            raise RuntimeError('King defence test timed out')
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
