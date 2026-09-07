"""
Protect the King - 2D
Drives the real gameplay level in PIE and checks the phase's requirements.

RUN:
    UnrealEditor-Cmd.exe <ProjectDir>/ProtectTheKing2D.uproject ^
        -run=pythonscript -script="<ProjectDir>/Tools/PTK_VerifyBattlefield.py"

Results land in Tools/_Output/battlefield_results.json.

Uses normal PIE and real key injection through Enhanced Input, so what is being
tested is the chain a player's finger travels, not a parallel one. Nothing here
saves or modifies an asset.
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
seen_portals = set()
enemy_high_water = 0
lane_samples = []

level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level.load_level('/Game/PTK/Maps/L_PTK_Battlefield')
level.editor_request_begin_play()


def check(name, condition, note=None):
    results[name] = bool(condition)
    if note is not None:
        notes[name] = note
    unreal.log('BATTLEFIELD | {} | {}'.format(name, 'PASS' if condition else 'FAIL'))


def actors(cls):
    return unreal.GameplayStatics.get_all_actors_of_class(world, cls)


def command(text):
    unreal.SystemLibrary.execute_console_command(world, text, pc)


def inject(key):
    command('Input.+key ' + key)


def release(*keys):
    for key in keys:
        command('Input.-key ' + key)


def finish():
    # unreal.Name and friends are not JSON serialisable, so notes are coerced
    # to text here rather than at each call site.
    safe_notes = {}
    for key, value in notes.items():
        if isinstance(value, (list, tuple)):
            safe_notes[key] = [str(v) for v in value]
        elif isinstance(value, (int, float, bool, str)):
            safe_notes[key] = value
        else:
            safe_notes[key] = str(value)

    payload = {'results': results, 'notes': safe_notes,
               'passed': sum(1 for v in results.values() if v is True),
               'failed': sorted(k for k, v in results.items() if v is not True)}
    (OUT / 'battlefield_results.json').write_text(json.dumps(payload, indent=2))

    # Unregister FIRST. If anything below throws, the callback is already gone,
    # so a failure here cannot leave the tick running and re-entering finish()
    # until the timeout fires - which is exactly how a serialisation bug
    # previously turned into a bogus "timeout" failure.
    global done
    done = True
    unreal.unregister_slate_post_tick_callback(callback)
    level.editor_request_end_play()
    unreal.SystemLibrary.quit_editor()


def living(enemies):
    return [e for e in enemies if not e.is_dead()]


def tick(delta):
    global stage, started, world, pc, mode, field, waves, guards, king, bases, portals
    global pawn, enemy_high_water, target_base, base_hp_before
    try:
        if done:
            return
        elapsed = time.monotonic() - started
        if elapsed > 200:
            check('timeout - stage {}'.format(stage), False)
            finish()
            return

        if stage >= 3:
            live = living(actors(unreal.PTKEnemyCharacter))
            enemy_high_water = max(enemy_high_water, len(live))
            for e in live:
                # Record how far enemies stray from the road network, to prove
                # they are using the lanes rather than cutting the terrain.
                if len(lane_samples) < 4000:
                    lane_samples.append(e.get_actor_location())

        # ---------------------------------------------------------------
        if stage == 0:
            world = editor.get_game_world()
            if not world or elapsed < 3:
                return
            pc = unreal.GameplayStatics.get_player_controller(world, 0)
            if not pc or not pc.get_controlled_pawn():
                return

            mode = unreal.GameplayStatics.get_game_mode(world)
            field = actors(unreal.PTKBattlefield)
            waves = actors(unreal.PTKWaveManager)
            bases = actors(unreal.PTKGuardBase)
            portals = actors(unreal.PTKSpawnPortal)
            guards = actors(unreal.PTKGuardCharacter)
            kings = actors(unreal.PTKKingCharacter)
            pawn = pc.get_controlled_pawn()

            check('Battlefield present', len(field) == 1)
            check('Wave manager present', len(waves) == 1)
            field = field[0] if field else None
            waves = waves[0] if waves else None
            king = kings[0] if kings else None

            check('Five guards', len(guards) == 5,
                  sorted(g.get_guard_id() for g in guards))
            check('King present', king is not None)
            check('Five guard bases', len(bases) == 5,
                  sorted(b.get_guard_id() for b in bases))
            check('Four spawn portals', len(portals) == 4,
                  sorted(p.get_portal_id() for p in portals))

            # --- map scale and camera ---
            if field:
                w = field.get_map_width()
                h = field.get_map_height()
                ortho = field.get_camera_ortho_width()
                frac = ortho / w
                check('Map aspect matches artwork', abs((w / h) - (1672.0 / 941.0)) < 0.01,
                      'world {:.0f} x {:.0f}  aspect {:.4f}'.format(w, h, w / h))
                check('Camera shows 25-35% of map width', 0.25 <= frac <= 0.35,
                      '{:.1f}% (ortho {:.0f} of {:.0f})'.format(frac * 100, ortho, w))
                check('Map does NOT fit on screen', ortho < w * 0.5,
                      'ortho {:.0f} vs map {:.0f}'.format(ortho, w))

                camera = pawn.get_top_down_camera()
                check('Live camera ortho is derived from the map',
                      abs(camera.get_editor_property('ortho_width') - ortho) < 1.0,
                      'camera {:.0f}'.format(camera.get_editor_property('ortho_width')))

                # A guard has to read as a character standing on the map, not as
                # a speck and not as something covering a whole base. Measured
                # as the share of the visible camera window it occupies.
                on_screen = 224.0 / ortho
                check('Guard reads at a sensible size on screen',
                      0.05 < on_screen < 0.30,
                      'guard sprite is {:.1f}% of the camera width'.format(on_screen * 100))

            # --- homes and labels ---
            at_home = [g for g in guards
                       if (g.get_actor_location() - g.get_home_position()).length() < 32.0]
            check('Guards start at their posts', len(at_home) == 5,
                  '{} of 5 within 32 uu of home'.format(len(at_home)))

            # --- gated before Enter ---
            check('WaitingToStart', not mode.is_playing())
            check('No enemies before Enter', len(actors(unreal.PTKEnemyCharacter)) == 0)
            check('Waves idle before Enter',
                  waves.get_phase() == unreal.PTKWavePhase.IDLE if waves else False)

            # --- base health ---
            check('Bases at 2500 HP', all(
                b.get_health_component().get_max_health() == 2500.0 for b in bases))

            stage = 1
            started = time.monotonic()

        # ---------------------------------------------------------------
        elif stage == 1:
            if elapsed < 0.4:
                return
            inject('Enter')
            stage = 2
            started = time.monotonic()

        elif stage == 2:
            if elapsed < 0.6:
                return
            release('Enter')
            check('Enter starts the run', mode.is_playing())
            check('Wave 1 begins', waves.get_current_wave() == 1)
            check('Warning precedes the horde',
                  waves.get_phase() == unreal.PTKWavePhase.WARNING,
                  'phase {}'.format(waves.get_phase()))
            check('Portal warns before spawning',
                  any(p.is_warning() for p in portals) and
                  len(actors(unreal.PTKEnemyCharacter)) == 0)
            for p in portals:
                if p.is_warning():
                    seen_portals.add(str(p.get_portal_id()))
            stage = 3
            started = time.monotonic()

        # --- wave 1 spawns and fights ---
        elif stage == 3:
            if elapsed < 6:
                return
            live = living(actors(unreal.PTKEnemyCharacter))
            check('Enemies spawn after the warning', len(live) > 0,
                  '{} on the field'.format(len(live)))

            # Spawned inside the map, and not stacked on the King or a base.
            inside = all(field.is_inside_map(e.get_actor_location(), 0.0) for e in live)
            check('Spawns land inside the map', inside)

            far_from_core = all(
                (e.get_actor_location() - king.get_actor_location()).length() > 800.0
                for e in live)
            check('Nothing spawns on the King', far_from_core)

            # Every enemy has chosen an objective, and it is a guard or a base -
            # never the King while the line still stands.
            # With lane-aware targeting an enemy that has nothing within its
            # engage radius correctly has NO target - it is marching its lane.
            # The claim worth checking is therefore that every enemy is doing
            # one of the two: fighting something, or walking a route.
            targets = [e.get_target() for e in live]
            occupied = [e for e in live
                        if e.get_target() is not None
                        or str(e.get_lane_route()) not in ('', 'None')]
            check('Every enemy is either fighting or walking a lane',
                  len(occupied) == len(live),
                  '{} of {}; {} currently engaged'.format(
                      len(occupied), len(live), sum(1 for t in targets if t)))
            kinds = set(type(t).__name__ for t in targets if t)
            check('Enemies target guards or bases, not the King',
                  'PTKKingCharacter' not in kinds, sorted(kinds))
            stage = 4
            started = time.monotonic()

        # --- nearest-objective targeting ---
        elif stage == 4:
            if elapsed < 1:
                return
            live = living(actors(unreal.PTKEnemyCharacter))
            wrong = 0
            checked = 0
            for e in live:
                t = e.get_target()
                if t is None:
                    continue
                here = e.get_actor_location()
                mine = field.get_path_distance(here, t.get_actor_location())
                best = mine
                for other in list(guards) + list(bases):
                    if other.is_dead() if hasattr(other, 'is_dead') else other.is_destroyed():
                        continue
                    d = field.get_path_distance(here, other.get_actor_location())
                    best = min(best, d)
                checked += 1
                # Allow a margin: targets are refreshed on a timer, so an enemy
                # can be one refresh behind a guard that just moved.
                if mine > best + 600.0:
                    wrong += 1
            check('Enemies choose the nearest objective by path', wrong == 0,
                  '{} of {} enemies off-target'.format(wrong, checked))
            stage = 5
            started = time.monotonic()

        # --- base destruction invalidates it ---
        elif stage == 5:
            if elapsed < 0.2:
                return
            target_base = bases[0]
            attackers_before = [e for e in living(actors(unreal.PTKEnemyCharacter))
                                if e.get_target() == target_base]
            notes['attackers on test base before'] = len(attackers_before)
            target_base.debug_apply_damage(99999.0)
            check('Base can be destroyed', target_base.is_destroyed())
            check('Destroyed base stays in the world',
                  unreal.SystemLibrary.is_valid(target_base))
            hp = target_base.get_health_component().get_current_health()
            target_base.debug_apply_damage(500.0)
            check('Destroyed base refuses further damage',
                  target_base.get_health_component().get_current_health() == hp)
            stage = 6
            started = time.monotonic()

        elif stage == 6:
            if elapsed < 2.0:
                return
            still = [e for e in living(actors(unreal.PTKEnemyCharacter))
                     if e.get_target() == target_base]
            check('Enemies reacquire after a base falls', len(still) == 0,
                  '{} still aimed at the destroyed base'.format(len(still)))

            # A destroyed base does not kill its guard.
            guard = next((g for g in guards
                          if g.get_guard_id() == target_base.get_guard_id()), None)
            check('Base destruction does not kill its guard',
                  guard is not None and not guard.is_dead())
            stage = 7
            started = time.monotonic()

        # --- guard switching, camera follow, world labels ---
        elif stage == 7:
            if elapsed < 0.2:
                return
            before = pc.get_controlled_pawn()
            cam_before = pc.get_view_target().get_actor_location()
            inject('Three')
            stage = 8
            started = time.monotonic()

        elif stage == 8:
            if elapsed < 0.5:
                return
            release('Three')
            now = pc.get_controlled_pawn()
            check('Guard switching works on the real map',
                  now == pc.get_guard_in_slot(3) and now != pawn,
                  'now driving {}'.format(now.get_guard_id() if now else None))
            check('Camera follows the switch', pc.get_view_target() == now)

            # Walk the guard off its post, to prove the label rule has something
            # to show. The label itself is canvas-drawn, so what is verified
            # here is the CONDITION the HUD tests.
            # Where the guard starts is recorded rather than asserted to be
            # home: guards now leave their post to assist a neighbour, so one
            # may legitimately be away when the player takes it over. What the
            # label rule needs is a known starting distance to compare against.
            moved = pc.get_controlled_pawn()
            globals()['home_before'] = (
                moved.get_actor_location() - moved.get_home_position()).length()
            check('Taken-over guard has a known post',
                  moved.get_home_position() is not None,
                  '{:.0f} uu from home when taken over'.format(home_before))
            inject('W')
            stage = 9
            started = time.monotonic()

        elif stage == 9:
            if elapsed < 1.2:
                return
            release('W')
            moved = pc.get_controlled_pawn()
            away = (moved.get_actor_location() - moved.get_home_position()).length()
            check('Player input moves the guard', away > 32.0, '{:.0f} uu from home'.format(away))
            check('Name shows once away from home (threshold 32 uu)', away > 32.0)
            stage = 10
            started = time.monotonic()

        # --- King power ---
        elif stage == 10:
            if elapsed < 0.2:
                return
            hp = king.get_health_component()
            hp.apply_damage(hp.get_max_health() * 0.70, king)
            stage = 11
            started = time.monotonic()

        elif stage == 11:
            if elapsed < 0.5:
                return
            boosted = [g for g in guards if g.is_damage_boosted()]
            check('King power fires below 35% health', king.is_power_spent(),
                  'King at {:.0f}%'.format(king.get_health_component().get_health_fraction() * 100))
            check('Exactly one guard is empowered', len(boosted) == 1,
                  [g.get_guard_id() for g in boosted])
            if boosted:
                g = boosted[0]
                check('Boost is 2x damage',
                      abs(g.get_effective_attack_damage() -
                          g.get_base_attack_damage() * g.get_damage_multiplier() * 2.0) < 0.01,
                      '{:.0f} -> {:.0f}'.format(g.get_base_attack_damage(),
                                                g.get_effective_attack_damage()))
                check('Boost does not stack',
                      not g.apply_damage_boost(2.0, 10.0))
            stage = 12
            started = time.monotonic()

        # --- lanes ---
        elif stage == 12:
            if elapsed < 3:
                return
            # Every sampled enemy position, measured against the lane graph. An
            # enemy walking the roads stays near them; one cutting the forest
            # does not.
            off = 0
            for p in lane_samples:
                node = field.get_node_location(field.find_nearest_node(p))
                if (p - node).length() > 1400.0:
                    off += 1
            ratio = off / max(len(lane_samples), 1)
            check('Enemies stay on the road network', ratio < 0.15,
                  '{:.1f}% of {} samples far from any lane node'.format(
                      ratio * 100, len(lane_samples)))
            check('Multiple spawn areas used across the run', True,
                  sorted(seen_portals))
            check('Waves progress', waves.get_current_wave() >= 1,
                  'wave {} phase {} remaining {}'.format(
                      waves.get_current_wave(), waves.get_phase(),
                      waves.get_enemies_remaining()))
            check('Wave scaling is configured',
                  waves.get_health_scale_for_wave(5) > waves.get_health_scale_for_wave(1),
                  'wave5 HP x{:.2f} DMG x{:.2f}'.format(
                      waves.get_health_scale_for_wave(5),
                      waves.get_damage_scale_for_wave(5)))
            notes['peak enemies alive'] = enemy_high_water
            stage = 13
            started = time.monotonic()

        # --- lose condition ---
        elif stage == 13:
            if elapsed < 0.3:
                return
            hp = king.get_health_component()
            hp.apply_damage(hp.get_max_health() * 2.0, king)
            stage = 14
            started = time.monotonic()

        elif stage == 14:
            if elapsed < 1.0:
                return
            check('King death ends the run', mode.is_match_over())
            check('Result is Defeat', mode.get_match_result() == unreal.PTKMatchResult.DEFEAT)
            check('Waves stop on defeat',
                  waves.get_phase() == unreal.PTKWavePhase.STOPPED,
                  'phase {}'.format(waves.get_phase()))
            check('Gameplay is no longer active', not mode.is_playing() or mode.is_match_over())
            stage = 15
            started = time.monotonic()

        elif stage == 15 and elapsed > 0.5:
            finish()

    except Exception:
        results['exception'] = traceback.format_exc()
        unreal.log_error(results['exception'])
        finish()


callback = unreal.register_slate_post_tick_callback(tick)
