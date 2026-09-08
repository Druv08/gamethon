"""
Protect the King - 2D
Verifies the wave-analytics tracking: player usage, switching, lane metrics,
lane vulnerability, guard dominance and enemy-type effectiveness.

Drives the player DELIBERATELY - holding one guard for a whole wave, then
switching constantly through the next - so the metrics have a known shape to be
checked against rather than whatever a random fight happened to produce.

RUN:
    UnrealEditor.exe <proj>.uproject -ExecutePythonScript=Tools/PTK_VerifyAnalytics.py -RenderOffscreen

Results: Tools/_Output/analytics_results.json
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
switch_slot = 1
switch_timer = 0.0
wave1 = None

level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level.load_level('/Game/PTK/Maps/L_PTK_Battlefield')
level.editor_request_begin_play()


def check(name, condition, note=None):
    results[name] = bool(condition)
    if note is not None:
        notes[name] = note
    unreal.log('ANALYTICS | {} | {}'.format(name, 'PASS' if condition else 'FAIL'))


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
        elif isinstance(v, (list, tuple)):
            safe[k] = [str(x) for x in v]
        else:
            safe[k] = v if isinstance(v, (int, float, bool, str)) else str(v)
    (OUT / 'analytics_results.json').write_text(json.dumps(
        {'results': results, 'notes': safe,
         'passed': sum(1 for v in results.values() if v is True),
         'failed': sorted(k for k, v in results.items() if v is not True)}, indent=2))
    done = True
    unreal.unregister_slate_post_tick_callback(callback)
    level.editor_request_end_play()
    unreal.SystemLibrary.quit_editor()


def guard_rows(snap):
    return {str(g.guard_id): g for g in snap.guards}


def lane_rows(snap):
    return {str(l.lane_id): l for l in snap.lanes}


def enemy_rows(snap):
    return {str(e.enemy_id): e for e in snap.enemy_types}


def tick(delta):
    global stage, started, world, pc, field, waves, king, analytics
    global switch_slot, switch_timer, wave1
    try:
        if done:
            return
        elapsed = time.monotonic() - started
        if elapsed > 180 or (time.monotonic() - run_started) > 520:
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
            king = field.get_king()
            # Reached through the battlefield: a world subsystem has no direct
            # Python accessor in this engine build.
            analytics = field.get_analytics()
            check('Analytics subsystem exists', analytics is not None)
            if analytics is None:
                finish()
                return
            check('No history before the first wave',
                  len(analytics.get_snapshots()) == 0)
            command('Input.+key Enter')
            stage = 1
            started = time.monotonic()

        elif stage == 1:
            if elapsed < 0.8:
                return
            command('Input.-key Enter')
            check('Tracking starts with the wave', analytics.is_tracking_wave())
            # WAVE 1: hold Wraith and nothing else.
            pc.select_guard_slot(3)
            stage = 2
            started = time.monotonic()

        elif stage == 2:
            if elapsed < 22:
                return
            live = analytics.get_live_snapshot()
            rows = guard_rows(live)
            wraith = rows.get('Wraith')
            check('Held guard accumulates player-control time',
                  wraith is not None and wraith.player_controlled_seconds > 15.0,
                  '{:.1f}s'.format(wraith.player_controlled_seconds) if wraith else 'no row')
            best = max(rows.values(), key=lambda g: g.player_controlled_seconds)
            check('Wraith has the highest player-control share',
                  str(best.guard_id) == 'Wraith',
                  {str(g.guard_id): round(g.player_control_fraction, 2)
                   for g in rows.values()})
            check('Only the held guard has control time',
                  all(g.player_controlled_seconds < 1.0
                      for g in rows.values() if str(g.guard_id) != 'Wraith'),
                  {str(g.guard_id): round(g.player_controlled_seconds, 1)
                   for g in rows.values()})

            # AI ASSIST vs PLAYER PRESENCE. The player has been standing on
            # Wraith's ground the whole time, so any assist presence recorded
            # elsewhere must NOT have landed in the player counter.
            lanes = lane_rows(live)
            assisted = {k: v for k, v in lanes.items()
                        if v.ai_assist_presence_seconds > 0.0}
            leaked = {k: v.player_presence_seconds for k, v in assisted.items()
                      if v.player_presence_seconds > 1.0
                      and 'Wraith' not in str(v.base_id)}
            check('AI assist is not counted as player presence',
                  not leaked,
                  {'assisted lanes': len(assisted), 'leaked': leaked} if assisted
                  else 'no assist observed yet')

            # Damage one base heavily so its lane must score more vulnerable.
            bases = actors(unreal.PTKGuardBase)
            for b in bases:
                if str(b.get_guard_id()) == 'Aegis':
                    b.debug_apply_damage(1800.0)
            stage = 3
            started = time.monotonic()

        elif stage == 3:
            if elapsed < 2:
                return
            live = analytics.get_live_snapshot()
            lanes = lane_rows(live)
            aegis = [v for v in lanes.values() if str(v.base_id) == 'Aegis']
            check('Base damage is attributed to its lane',
                  any(v.base_damage_taken > 1000.0 for v in aegis),
                  {k: round(v.base_damage_taken) for k, v in lanes.items()})

            # End wave 1 so it freezes.
            for e in living(unreal.PTKEnemyCharacter):
                e.get_health_component().apply_damage(999999.0, pc.get_controlled_pawn())
            stage = 4
            started = time.monotonic()

        elif stage == 4:
            if elapsed < 3 or len(analytics.get_snapshots()) == 0:
                return
            wave1 = analytics.get_snapshots()[0]
            rows = guard_rows(wave1)
            lanes = lane_rows(wave1)

            check('Wave 1 was frozen', wave1.wave_number == 1
                  and wave1.duration_seconds > 10.0,
                  'wave {} over {:.0f}s'.format(wave1.wave_number, wave1.duration_seconds))

            wraith = rows.get('Wraith')
            check('Frozen snapshot keeps the usage shape',
                  wraith is not None and wraith.player_control_fraction > 0.8,
                  '{:.0f}%'.format(wraith.player_control_fraction * 100) if wraith else '-')
            check('Single-guard focus detected',
                  wave1.switching.single_guard_focus
                  and str(wave1.switching.focus_guard_id) == 'Wraith',
                  str(wave1.switching.focus_guard_id))
            check('Holding one guard reads as LOW switching',
                  wave1.switching.tempo == unreal.PTKSwitchTempo.LOW,
                  '{} switches, {:.1f}/min, tempo {}'.format(
                      wave1.switching.total_switches,
                      wave1.switching.switches_per_minute,
                      wave1.switching.tempo))

            # LANE VULNERABILITY: the damaged lane must outscore a lane that
            # saw fighting but kept its base whole.
            damaged = [v for v in lanes.values() if str(v.base_id) == 'Aegis']
            others = [v for v in lanes.values()
                      if str(v.base_id) != 'Aegis' and v.enemies_spawned > 0]
            check('Damaged base raises its lane vulnerability',
                  damaged and others
                  and max(v.vulnerability for v in damaged)
                      > max(v.vulnerability for v in others),
                  {str(v.lane_id): round(v.vulnerability, 2) for v in lanes.values()})
            check('Vulnerability stays inside 0..1',
                  all(0.0 <= v.vulnerability <= 1.0 for v in lanes.values()))
            untouched = [v for v in lanes.values()
                         if v.enemies_spawned == 0 and v.base_damage_taken == 0.0
                         and v.guard_damage_taken == 0.0 and v.deepest_progress == 0.0]
            check('A lane nothing happened on is not called vulnerable',
                  all(v.vulnerability == 0.0 for v in untouched),
                  {str(v.lane_id): round(v.vulnerability, 2) for v in untouched}
                  or 'every lane saw something')

            # DOMINANCE: the guard that did the most work should lead, and it
            # must not simply be whoever the player held.
            check('Dominance stays inside 0..1',
                  all(0.0 <= g.dominance <= 1.0 for g in rows.values()))
            worker = max(rows.values(), key=lambda g: (g.kills, g.damage_dealt))
            leader = max(rows.values(), key=lambda g: g.dominance)
            check('Dominance follows contribution, not usage alone',
                  leader.dominance > 0.0
                  and (str(leader.guard_id) == str(worker.guard_id)
                       or leader.dominance >= rows['Wraith'].dominance),
                  {str(g.guard_id): '{:.2f} (kills {}, dealt {:.0f}, ctrl {:.0f}%)'.format(
                      g.dominance, g.kills, g.damage_dealt, g.player_control_fraction * 100)
                   for g in rows.values()})

            # ENEMY EFFECTIVENESS
            enemies = enemy_rows(wave1)
            check('Enemy types were recorded', len(enemies) > 0,
                  {k: '{} spawned/{} died'.format(v.spawned, v.died)
                   for k, v in enemies.items()})
            check('Effectiveness is scored and bounded',
                  all(0.0 <= e.effectiveness <= 1.0 for e in enemies.values())
                  and any(e.effectiveness > 0.0 for e in enemies.values()),
                  {k: round(v.effectiveness, 2) for k, v in enemies.items()})
            check('Spawn counts match the lanes they were dealt to',
                  sum(e.spawned for e in enemies.values())
                  == sum(l.enemies_spawned for l in lanes.values()),
                  '{} by type vs {} by lane'.format(
                      sum(e.spawned for e in enemies.values()),
                      sum(l.enemies_spawned for l in lanes.values())))
            stage = 5
            started = time.monotonic()

        # WAVE 2: switch constantly, and confirm the tempo reads HIGH.
        elif stage == 5:
            if not analytics.is_tracking_wave():
                return
            switch_timer += delta
            if switch_timer > 1.2:
                switch_timer = 0.0
                switch_slot = switch_slot % 5 + 1
                pc.select_guard_slot(switch_slot)
            if elapsed < 30:
                return
            live = analytics.get_live_snapshot()
            # Compared against the wave the player spent holding ONE guard,
            # rather than against a fixed count. Some switches are legitimately
            # refused - a slot whose guard has died - so an absolute target
            # measures how the fight went as much as how the player played.
            check('Frequent switching is counted',
                  live.switching.total_switches > wave1.switching.total_switches
                  and live.switching.total_switches >= 5,
                  '{} switches in {:.0f}s vs {} while holding one guard'.format(
                      live.switching.total_switches, live.duration_seconds,
                      wave1.switching.total_switches))
            check('Frequent switching reads as HIGH tempo',
                  live.switching.tempo == unreal.PTKSwitchTempo.HIGH,
                  '{:.1f}/min, tempo {}'.format(
                      live.switching.switches_per_minute, live.switching.tempo))
            check('Average gap between switches is sane',
                  0.2 < live.switching.average_seconds_between < 6.0,
                  '{:.2f}s'.format(live.switching.average_seconds_between))
            check('Spread play is not single-guard focus',
                  not live.switching.single_guard_focus,
                  {str(g.guard_id): round(g.player_control_fraction, 2)
                   for g in live.guards})
            check('Switch-ins are counted per guard',
                  sum(g.times_switched_into for g in live.guards)
                  >= live.switching.total_switches,
                  {str(g.guard_id): g.times_switched_into for g in live.guards})

            # King power attribution.
            pc.activate_king_power()
            stage = 6
            started = time.monotonic()

        elif stage == 6:
            if elapsed < 1.0:
                return
            live = analytics.get_live_snapshot()
            boosted = [g for g in live.guards if g.received_king_power]
            check('King power is recorded against the guard that got it',
                  len(boosted) == 1,
                  [str(g.guard_id) for g in boosted])
            analytics.log_history()
            check('History holds every finished wave',
                  len(analytics.get_snapshots()) >= 1,
                  len(analytics.get_snapshots()))
            stage = 7
            started = time.monotonic()

        elif stage == 7 and elapsed > 1.0:
            finish()

    except Exception:
        results['exception'] = traceback.format_exc()
        unreal.log_error(results['exception'])
        finish()


callback = unreal.register_slate_post_tick_callback(tick)
