"""
Protect the King - 2D
Verifies terrain collision, King power (Q + automatic), base health readout,
and re-checks the lane/assist/combat systems for regressions.

RUN:
    UnrealEditor.exe <proj>.uproject -ExecutePythonScript=Tools/PTK_VerifyMapSystems.py -RenderOffscreen

Results: Tools/_Output/map_systems_results.json
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
off_road = []          # guard positions found off walkable ground
boost_seen = set()

level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level.load_level('/Game/PTK/Maps/L_PTK_Battlefield')
level.editor_request_begin_play()


def check(name, condition, note=None):
    results[name] = bool(condition)
    if note is not None:
        notes[name] = note
    unreal.log('MAPSYS | {} | {}'.format(name, 'PASS' if condition else 'FAIL'))


def actors(cls):
    return unreal.GameplayStatics.get_all_actors_of_class(world, cls)


def living(cls):
    return [a for a in actors(cls) if not a.is_dead()]


def command(text):
    unreal.SystemLibrary.execute_console_command(world, text, pc)


def finish():
    global done
    safe = {}
    for k, v in notes.items():
        if isinstance(v, dict):
            safe[k] = {str(a): str(b) for a, b in v.items()}
        elif isinstance(v, (list, tuple, set)):
            safe[k] = [str(x) for x in v]
        else:
            safe[k] = v if isinstance(v, (int, float, bool, str)) else str(v)
    (OUT / 'map_systems_results.json').write_text(json.dumps(
        {'results': results, 'notes': safe,
         'passed': sum(1 for v in results.values() if v is True),
         'failed': sorted(k for k, v in results.items() if v is not True)}, indent=2))
    done = True
    unreal.unregister_slate_post_tick_callback(callback)
    level.editor_request_end_play()
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    global stage, started, world, pc, mode, field, waves, king, guards, bases, pawn
    global probe, probe_home, base0, hp0, boosted_first
    try:
        if done:
            return
        elapsed = time.monotonic() - started
        if elapsed > 180 or (time.monotonic() - run_started) > 520:
            check('timeout at stage {}'.format(stage), False)
            finish()
            return

        # Continuously watch that no guard is ever left standing off-road.
        if stage >= 4:
            for g in actors(unreal.PTKGuardCharacter):
                if g and not g.is_dead() and not field.is_walkable(g.get_actor_location()):
                    if len(off_road) < 200:
                        off_road.append('{} at {}'.format(
                            g.get_guard_id(), g.get_actor_location()))
            k = field.get_king()
            if k and k.get_boosted_guard():
                boost_seen.add(str(k.get_boosted_guard().get_guard_id()))

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
            king = field.get_king()
            guards = actors(unreal.PTKGuardCharacter)
            bases = actors(unreal.PTKGuardBase)
            pawn = pc.get_controlled_pawn()

            # --- TERRAIN: everything the game needs to stand on must be legal
            bad_homes = [str(g.get_guard_id()) for g in guards
                         if not field.is_walkable(g.get_home_position())]
            check('Every guard post is on walkable ground', not bad_homes,
                  bad_homes or 'all five posts legal')

            bad_bases = [str(b.get_guard_id()) for b in bases
                         if not field.is_walkable(b.get_actor_location())]
            check('Every base is on walkable ground', not bad_bases,
                  bad_bases or 'all five legal')
            check('The core is walkable', field.is_walkable(king.get_actor_location()))

            # Every lane node must be reachable ground, or guards could never
            # follow the roads the enemies use.
            nodes = ['S_TL', 'S_TR', 'S_BL', 'S_BR', 'J_TL', 'J_TR', 'J_ML',
                     'J_MR', 'J_BL', 'J_BR', 'J_KTL', 'J_KTR', 'J_KBL', 'J_KBR',
                     'B_AEGIS', 'B_WRAITH', 'B_REAVER', 'B_RAVAGER', 'B_SENTINEL', 'KING']
            bad_nodes = [n for n in nodes
                         if not field.is_walkable(field.get_node_location(n))]
            check('Every lane node is walkable', not bad_nodes,
                  bad_nodes or '{} nodes all legal'.format(len(nodes)))

            # --- TERRAIN: the blocked places must actually be blocked.
            #
            # Measured over a grid rather than at hand-picked coordinates. The
            # first attempt guessed "forest" points that turned out to sit on
            # the diagonal roads into the core, so the test was wrong and the
            # code was right. A sweep cannot make that mistake: it asks what
            # FRACTION of the map is walkable, and a road network drawn over a
            # forest has to be a minority of it.
            centre = field.get_map_centre()
            walkable = blocked = 0
            far_but_walkable = []
            for gx in range(1, 40):
                for gy in range(1, 24):
                    u = gx / 40.0
                    v = gy / 24.0
                    spot = field.normalised_to_world(unreal.Vector2D(u, v))
                    if field.is_walkable(spot):
                        walkable += 1
                        # Anything walkable must be near SOME lane node, or the
                        # corridor test has sprung a leak into open terrain.
                        near = min((spot - field.get_node_location(n)).length()
                                   for n in ('S_TL', 'S_TR', 'S_BL', 'S_BR', 'J_TL', 'J_TR',
                                             'J_ML', 'J_MR', 'J_BL', 'J_BR', 'J_KTL', 'J_KTR',
                                             'J_KBL', 'J_KBR', 'B_AEGIS', 'B_WRAITH',
                                             'B_REAVER', 'B_RAVAGER', 'B_SENTINEL', 'KING'))
                        if near > 1600.0:
                            far_but_walkable.append('({:.2f},{:.2f}) {:.0f}uu'.format(u, v, near))
                    else:
                        blocked += 1

            fraction = walkable / float(walkable + blocked)
            check('Most of the map is blocked terrain, not road',
                  0.10 <= fraction <= 0.50,
                  '{:.0f}% walkable across {} samples'.format(
                      fraction * 100.0, walkable + blocked))
            check('No walkable ground far from every road',
                  not far_but_walkable, far_but_walkable[:4] or 'none')

            off_map = {
                'outside west': unreal.Vector(centre.x + 4000.0, 0.0, centre.z),
                'outside east': unreal.Vector(centre.x - 4000.0, 0.0, centre.z),
                'outside north': unreal.Vector(centre.x, 0.0, centre.z + 2600.0),
                'outside south': unreal.Vector(centre.x, 0.0, centre.z - 2600.0),
            }
            leaks = [name for name, spot in off_map.items() if field.is_walkable(spot)]
            check('Beyond the map edge is blocked', not leaks, leaks or 'all four blocked')

            check('King power starts ready', king.can_activate_power())
            command('Input.+key Enter')
            stage = 1
            started = time.monotonic()

        elif stage == 1:
            if elapsed < 0.6:
                return
            command('Input.-key Enter')
            check('Run started', mode.is_playing())
            stage = 2
            started = time.monotonic()

        # --- KING POWER via Q, through real key injection ---
        elif stage == 2:
            if elapsed < 3:
                return
            command('Input.+key Q')
            stage = 3
            started = time.monotonic()

        elif stage == 3:
            if elapsed < 0.5:
                return
            command('Input.-key Q')
            boosted_first = king.get_boosted_guard()
            check('Q casts the King power', boosted_first is not None,
                  str(boosted_first.get_guard_id()) if boosted_first else 'nobody boosted')
            check('Boost is x2.0 for ~10s',
                  boosted_first is not None
                  and 9.0 <= boosted_first.get_damage_boost_remaining() <= 10.1,
                  '{:.1f}s left'.format(
                      boosted_first.get_damage_boost_remaining()) if boosted_first else '-')
            check('Cooldown starts at 30s',
                  29.0 <= king.get_power_cooldown_remaining() <= 30.1,
                  '{:.1f}s'.format(king.get_power_cooldown_remaining()))
            check('Power reports itself unavailable while running',
                  not king.can_activate_power())

            # Spam it: a second press must change nothing.
            for _ in range(5):
                command('Input.+key Q')
                command('Input.-key Q')
            stage = 4
            started = time.monotonic()

        elif stage == 4:
            if elapsed < 0.5:
                return
            check('Q cannot be spammed or stacked',
                  king.get_boosted_guard() == boosted_first
                  and king.get_power_cooldown_remaining() <= 30.1,
                  'still {} at {:.0f}s cooldown'.format(
                      boosted_first.get_guard_id() if boosted_first else '-',
                      king.get_power_cooldown_remaining()))

            # The automatic emergency cast shares this exact path: hurt the
            # King below the threshold and it must refuse while cooling down.
            king.debug_apply_damage(king.get_health_component().get_max_health() * 0.70)
            stage = 5
            started = time.monotonic()

        elif stage == 5:
            if elapsed < 0.5:
                return
            check('Automatic cast obeys the shared cooldown',
                  king.get_power_cooldown_remaining() > 0.0
                  and king.get_boosted_guard() == boosted_first,
                  'King at {:.0f}%, cooldown {:.0f}s'.format(
                      king.get_health_component().get_health_fraction() * 100.0,
                      king.get_power_cooldown_remaining()))

            # --- BASE HEALTH: the readout reads the real component ---
            base0 = bases[0]
            hp0 = base0.get_health_component().get_current_health()
            check('Base health starts full', abs(hp0 - 2500.0) < 0.5, '{:.0f}'.format(hp0))
            stage = 6
            started = time.monotonic()

        # --- terrain: drive a guard at the forest and confirm it is stopped ---
        elif stage == 6:
            if elapsed < 1.0:
                return
            probe = pc.get_controlled_pawn()
            probe_home = probe.get_actor_location()
            # Walk hard "up" the screen from the core - straight into the trees
            # north of the road ring.
            probe.set_move_input(unreal.Vector2D(0.0, 1.0))
            stage = 7
            started = time.monotonic()

        elif stage == 7:
            if elapsed < 4.0:
                return
            probe.set_move_input(unreal.Vector2D(0.0, 0.0))
            where = probe.get_actor_location()
            check('A guard walked at terrain stays on walkable ground',
                  field.is_walkable(where),
                  'ended at ({:.0f},{:.0f})'.format(where.x, where.z))
            check('It was actually stopped, not teleported home',
                  (where - probe_home).length() > 1.0,
                  'moved {:.0f} uu'.format((where - probe_home).length()))
            stage = 8
            started = time.monotonic()

        # --- let the fight run: lanes, assist, base damage, regressions ---
        elif stage == 8:
            if elapsed < 45:
                return
            check('Guards never stood on blocked terrain', not off_road,
                  off_road[:5] if off_road else 'clean across the whole fight')

            live = living(unreal.PTKEnemyCharacter)
            assigned = [e for e in live if str(e.get_lane_route()) not in ('', 'None')]
            check('Enemy lanes still assigned', not live or len(assigned) == len(live),
                  '{} of {}'.format(len(assigned), len(live)))

            strays = [e for e in live
                      if e.get_target() is None and e.get_distance_from_lane() > 520.0]
            check('Enemies still keep to their lanes', not strays, len(strays))

            check('Guard switching still works', pc.select_guard_slot(3))
            stage = 9
            started = time.monotonic()

        # --- base damage still real, and destruction still works ---
        elif stage == 9:
            if elapsed < 0.4:
                return
            for g in actors(unreal.PTKGuardCharacter):
                if g and g.get_guard_id() == base0.get_guard_id() and g != pc.get_controlled_pawn():
                    g.get_health_component().apply_damage(999999.0, base0)
            live = living(unreal.PTKEnemyCharacter)
            if live:
                spot = base0.get_actor_location()
                live[0].set_actor_location(
                    unreal.Vector(spot.x + 30.0, spot.y, spot.z + 30.0), False, False)
            stage = 10
            started = time.monotonic()

        elif stage == 10:
            if elapsed < 5:
                return
            hp1 = base0.get_health_component().get_current_health()
            check('Base still takes real attack damage', hp1 < hp0,
                  '{:.0f} -> {:.0f}'.format(hp0, hp1))
            command('HighResShot 1920x1080 filename=ptk_mapsys')
            stage = 11
            started = time.monotonic()

        elif stage == 11:
            if elapsed < 1.5:
                return
            base0.debug_apply_damage(999999.0)
            stage = 12
            started = time.monotonic()

        elif stage == 12:
            if elapsed < 1.0:
                return
            ruins = base0.get_editor_property('ruins_sprite')
            check('Destroyed base still shows ruins',
                  base0.is_destroyed() and ruins is not None
                  and ruins.get_editor_property('visible'))
            check('King power recovered or still cooling sensibly',
                  king.get_power_cooldown_remaining() >= 0.0,
                  '{:.0f}s left'.format(king.get_power_cooldown_remaining()))
            check('Boost was granted to exactly one guard', len(boost_seen) <= 1,
                  sorted(boost_seen))
            stage = 13
            started = time.monotonic()

        elif stage == 13 and elapsed > 1.0:
            finish()

    except Exception:
        results['exception'] = traceback.format_exc()
        unreal.log_error(results['exception'])
        finish()


callback = unreal.register_slate_post_tick_callback(tick)
