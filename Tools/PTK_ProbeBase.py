"""Focused diagnostic: why does an enemy attack not damage a guard base?

Drops a real enemy right on a base, waits for it to acquire and swing, and
reports the base's health along with the probe's own overlap result.
"""
import json
import time
import traceback
from pathlib import Path
import unreal

unreal.EditorPythonScripting.set_keep_python_script_alive(True)
OUT = Path(unreal.Paths.project_dir()) / "Tools/_Output"
OUT.mkdir(parents=True, exist_ok=True)

report = []
done = False
stage = 0
started = time.monotonic()

level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level.load_level('/Game/PTK/Maps/L_PTK_Battlefield')
level.editor_request_begin_play()


def say(text):
    report.append(str(text))
    unreal.log('PROBE-PY | ' + str(text))


def finish():
    global done
    (OUT / 'base_probe.txt').write_text('\n'.join(report) + '\n')
    done = True
    unreal.unregister_slate_post_tick_callback(callback)
    level.editor_request_end_play()
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    global stage, started, world, pc, base, enemy, hp0
    try:
        if done:
            return
        elapsed = time.monotonic() - started
        if elapsed > 90:
            say('TIMEOUT at stage {}'.format(stage))
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
            if elapsed < 0.5:
                return
            unreal.SystemLibrary.execute_console_command(world, 'Input.-key Enter', pc)
            stage = 2
            started = time.monotonic()

        elif stage == 2:
            if elapsed < 8:
                return
            bases = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.PTKGuardBase)
            base = bases[0]
            enemies = [e for e in unreal.GameplayStatics.get_all_actors_of_class(
                world, unreal.PTKEnemyCharacter) if not e.is_dead()]
            if not enemies:
                say('no enemies yet')
                return

            enemy = enemies[0]
            spot = base.get_actor_location()

            # Kill the guard that stands in front of this base, so the enemy has
            # nothing nearer than the base itself to pick.
            guards = unreal.GameplayStatics.get_all_actors_of_class(
                world, unreal.PTKGuardCharacter)
            for g in guards:
                if g.get_guard_id() == base.get_guard_id() and g != pc.get_controlled_pawn():
                    g.get_health_component().apply_damage(999999.0, base)
                    say('cleared guard {} from the base'.format(g.get_guard_id()))

            # Place the enemy just off the base centre - inside its own reach.
            enemy.set_actor_location(
                unreal.Vector(spot.x + 30.0, spot.y, spot.z + 30.0), False, False)
            hp0 = base.get_health_component().get_current_health()
            say('base {} HP before = {:.0f}'.format(base.get_guard_id(), hp0))
            say('enemy {} reach={:.0f} hitRadius={:.0f}'.format(
                enemy.get_enemy_id(), enemy.get_attack_reach(), enemy.get_attack_hit_radius()))
            stage = 3
            started = time.monotonic()

        elif stage == 3:
            if elapsed < 1.5:
                return
            say('after 1.5s: enemy state={} target={} dist={:.0f}'.format(
                enemy.get_enemy_state(),
                enemy.get_target().get_name() if enemy.get_target() else None,
                (enemy.get_actor_location() - base.get_actor_location()).length()))
            unreal.SystemLibrary.execute_console_command(
                world, 'PTKBaseProbe ' + str(base.get_guard_id()), pc)
            stage = 4
            started = time.monotonic()

        elif stage == 4:
            if elapsed < 6:
                return
            hp1 = base.get_health_component().get_current_health()
            say('base HP after ~7s = {:.0f}  (lost {:.0f})'.format(hp1, hp0 - hp1))
            say('enemy state={} target={} alive={}'.format(
                enemy.get_enemy_state(),
                enemy.get_target().get_name() if enemy.get_target() else None,
                not enemy.is_dead()))
            finish()

    except Exception:
        say(traceback.format_exc())
        finish()


callback = unreal.register_slate_post_tick_callback(tick)
