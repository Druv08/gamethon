"""Deterministic PIE combat checks. Only transient actors/settings are changed.

Run UnrealEditor -ExecutePythonScript=<this file> -RenderOffscreen -unattended.
The existing start-screen verifier separately exercises real mapped Enter/input.
"""
import json
import time
import traceback
from pathlib import Path
import unreal

OUT=Path(unreal.Paths.project_dir())/'Tools/_Output'
OUT.mkdir(parents=True,exist_ok=True)
results={}
STATS={'Infiltrator':(120,20,280,1.25),'Hijacker':(180,25,230,1.5),
       'Encrypter':(350,35,150,1),'Exfiltrator':(160,20,190,5)}
CLASSES={n:unreal.EditorAssetLibrary.load_asset('/Game/PTK/Characters/Enemies/'+n+'/Blueprints/BP_'+n).generated_class() for n in STATS}
CLASSES['SwarmNode']=unreal.EditorAssetLibrary.load_asset('/Game/PTK/Characters/Enemies/SwarmNode/Blueprints/BP_SwarmNode').generated_class()
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
level.load_level('/Game/PTK/Maps/L_PTK_TestGround')
level.editor_request_begin_play()
world=None
deadline=0.
started=time.monotonic()


def check(label,ok,detail=None):
    results[label]={'pass':bool(ok),'detail':detail}
    unreal.log('ROSTER TEST | '+label+' | '+('PASS' if ok else 'FAIL')+' | '+str(detail))


def actors(cls):return unreal.GameplayStatics.get_all_actors_of_class(world,cls)
def health(a):return a.get_health_component()
def hp(a):return health(a).get_current_health()
def move(a,v):a.set_actor_location(v,False,True)
def freeze(a):
    a.set_move_input(unreal.Vector2D(0,0))
    a.set_actor_tick_enabled(False)
    a.get_component_by_class(unreal.CharacterMovementComponent).stop_movement_immediately()
    a.get_component_by_class(unreal.CharacterMovementComponent).set_component_tick_enabled(False)
    if a.get_controller() and a.get_controller()!=pc:a.get_controller().set_actor_tick_enabled(False)


def spawn(name,offset,delay=None):
    for shot in actors(unreal.PTKProjectile):shot.destroy_actor()
    spawner.clear_wave()
    entry=unreal.PTKEnemySpawnEntry();entry.set_editor_property('enemy_class',CLASSES[name]);entry.set_editor_property('count',1)
    spawner.set_editor_property('additional_enemies',[entry]);spawner.set_editor_property('spawn_count',0)
    spawner.set_editor_property('ring_radius',0.);spawner.set_editor_property('position_jitter',0.)
    move(spawner,origin+offset)
    cdo=unreal.get_default_object(CLASSES[name]);previous=cdo.get_editor_property('initial_attack_delay')
    if delay is not None:cdo.set_editor_property('initial_attack_delay',delay)
    try:assert spawner.spawn_wave()==1
    finally:cdo.set_editor_property('initial_attack_delay',previous)
    enemy=actors(unreal.PTKEnemyCharacter)[0]
    # The existing spawner is a rootless helper actor. Position the transient
    # character itself for isolated tests; the saved development ring is intact.
    move(enemy,origin+offset)
    return enemy


def arrange():
    for i,g in enumerate(guards):
        freeze(g);move(g,origin+right*(i*1000));health(g).reset_health()


def run():
    global world,pc,spawner,guards,origin,right,king
    while not editor.get_game_world():yield .2
    world=editor.get_game_world()
    yield 2.
    pc=unreal.GameplayStatics.get_player_controller(world,0)
    mode=unreal.GameplayStatics.get_game_mode(world)
    guards=actors(unreal.PTKGuardCharacter)
    spawner=actors(unreal.PTKEnemySpawner)[0]
    king=actors(unreal.PTKKingCharacter)[0]
    check('before_start_no_enemies',len(actors(unreal.PTKEnemyCharacter))==0)
    check('before_start_spawner_refuses',spawner.spawn_wave()==0)
    check('five_guards_and_king',len(guards)==5 and king is not None)
    for g in guards:freeze(g)
    unreal.SystemLibrary.execute_console_command(world,'Input.+key Enter',pc)
    yield .3
    unreal.SystemLibrary.execute_console_command(world,'Input.-key Enter',pc)
    check('Enter_StartGame',mode.is_playing())
    enemies=actors(unreal.PTKEnemyCharacter)
    counts={n:sum(str(e.get_enemy_id())==n for e in enemies) for n in STATS}
    check('five_of_each_spawn',all(c==5 for c in counts.values()),counts)
    locs=[e.get_actor_location() for e in enemies]
    check('distinct_spawn_locations',all((a-b).length()>1 for i,a in enumerate(locs) for b in locs[i+1:]))
    spawner.set_editor_property('spawn_count',0);spawner.set_editor_property('additional_enemies',[])
    check('zero_counts_clear_development_spawn',spawner.spawn_wave()==0 and not actors(unreal.PTKEnemyCharacter))
    right=guards[0].get_movement_right_vector()
    origin=unreal.Vector(0,guards[0].get_actor_location().y,0)
    for slot in range(1,6):
        check('guard_switch_'+str(slot),pc.select_guard_slot(slot) or pc.get_controlled_pawn()==pc.get_guard_in_slot(slot))
        check('guard_selected_'+str(slot),pc.get_controlled_pawn()==pc.get_guard_in_slot(slot))
    pc.select_guard_slot(1)
    speeds={}
    for name,(maxhp,damage,speed,reach) in STATS.items():
        arrange();e=spawn(name,right*-500)
        check(name+'_stats',hp(e)==maxhp and e.get_editor_property('attack_damage')==damage and
              e.get_editor_property('max_move_speed')==speed and abs(e.get_attack_reach()-reach*64)<.01)
        animation_ok=True
        for anim in ['Idle','Walk','Attack']:
            for d in ['Down','Up','Left','Right']:
                fb=e.get_editor_property(anim.lower()+'_flipbooks').get_editor_property(d.lower())
                animation_ok=animation_ok and fb.get_name()=='FB_'+name+'_'+anim+'_'+d
                if anim=='Idle':
                    e.set_facing_direction(getattr(unreal.PTKFacingDirection,d.upper()))
                    animation_ok=animation_ok and e.get_sprite().get_flipbook()==fb
        check(name+'_four_direction_animations',animation_ok)
        yield .35
        speeds[name]=e.get_velocity().length()
        check(name+'_moves',speeds[name]>speed*.8,speeds[name])
        check(name+'_nearest_guard',e.get_target()==guards[0])
        damage_steps=[];previous=hp(guards[0]);attacks=False
        for _ in range(100):
            attacks=attacks or e.is_attacking()
            current=hp(guards[0])
            if current<previous:damage_steps.append(previous-current)
            previous=current
            if len(damage_steps)>=2:break
            yield .06
        check(name+'_attacks_exact_damage',attacks and len(damage_steps)>=2 and all(abs(d-damage)<.01 for d in damage_steps),damage_steps)
        check(name+'_no_friendly_fire',hp(e)==maxhp)
        if name=='Exfiltrator':
            check(name+'_ranged_stop',200<e.get_distance_to_target()<=321 and e.get_velocity().length()<1,e.get_distance_to_target())
        player=pc.get_controlled_pawn()
        move(player,e.get_actor_location()+(guards[0].get_actor_location()-e.get_actor_location())*.5)
        yield .55
        check(name+'_targets_player_guard_equally',e.get_target()==player)
        check(name+'_takes_damage',health(e).apply_damage(7,guards[0])==7 and hp(e)==maxhp-7)
        health(e).apply_damage(10000,guards[0]);deadpos=e.get_actor_location()
        check(name+'_death_state',e.is_dead() and e.get_enemy_state()==unreal.PTKEnemyState.DEAD and e.get_target() is None)
        check(name+'_dead_cannot_attack',not e.start_attack())
        yield .4
        check(name+'_death_stops_movement',(e.get_actor_location()-deadpos).length()<.1)
        sprite=e.get_sprite()
        check(name+'_death_flipbook',sprite.get_flipbook().get_name()=='FB_'+name+'_Death')
    check('Encrypter_slowest',speeds['Encrypter']<min(v for k,v in speeds.items() if k!='Encrypter'),speeds)

    # Real attacks in every direction, including projectile travel for Exfiltrator.
    up=guards[0].get_movement_up_vector()
    for name,(_,damage,_,reach) in STATS.items():
        for d,bearing in [('Right',right),('Left',right*-1),('Up',up),('Down',up*-1)]:
            arrange();e=spawn(name,bearing*(-reach*64*.7))
            before=hp(guards[0]);yield 1.3
            check(name+'_attack_'+d,e.get_facing_direction()==getattr(unreal.PTKFacingDirection,d.upper()) and
                  abs(before-hp(guards[0])-damage)<.01,before-hp(guards[0]))

    # No overlap damage: attacks delayed while two bodies occupy the same point.
    for name in STATS:
        arrange();e=spawn(name,unreal.Vector(0,0,0),100.)
        before=hp(guards[0]);yield .5
        check(name+'_no_touch_damage',hp(guards[0])==before)

    # The projectile may only hit its launch target, even if another guard
    # becomes nearer and crosses its path while it is already in flight.
    arrange();e=spawn('Exfiltrator',right*-220+up*-130)
    shot=None
    for _ in range(150):
        shots=[s for s in actors(unreal.PTKProjectile) if s.get_source_actor()==e and not s.is_spent()]
        if shots:shot=shots[0];break
        yield .01
    check('projectile_created',shot is not None)
    before=[hp(g) for g in guards]
    if shot:
        e.set_editor_property('attack_cooldown',100.)
        move(guards[1],origin-right*110-up*65)
        yield .6
        deltas=[b-hp(g) for b,g in zip(before,guards)]
        check('projectile_only_intended_target',deltas==[20,0,0,0,0],deltas)
        check('projectile_diagonal_aim',deltas[0]==20,deltas[0])

    # Existing guards still perform their own melee/projectile attacks.
    for slot in range(1,6):
        arrange();pc.select_guard_slot(slot);g=pc.get_controlled_pawn()
        move(g,origin)
        for other in guards:
            if other!=g:move(other,origin+right*(2000+guards.index(other)*500))
        e=spawn('Encrypter',right*120,100.);freeze(e)
        g.set_actor_tick_enabled(True)
        g.set_facing_direction(unreal.PTKFacingDirection.RIGHT)
        before=hp(e);accepted=g.start_attack()
        yield 1.
        check(str(g.get_guard_id())+'_combat_regression',accepted and hp(e)<before,before-hp(e))
        freeze(g)
    pc.select_guard_slot(1)

    arrange();e=spawn('SwarmNode',right*-300)
    expected=e.get_editor_property('attack_damage');before=hp(guards[0])
    yield .35
    check('SwarmNode_moves',e.get_velocity().length()>1)
    for _ in range(80):
        if hp(guards[0])<before:break
        yield .05
    check('SwarmNode_combat_regression',before-hp(guards[0])==expected,before-hp(guards[0]))
    health(e).apply_damage(10000,guards[0]);yield .1
    check('SwarmNode_death_regression',e.is_dead())

    # One dying guard at a time: all four types must leave dead guards, then King.
    arrange();spawner.clear_wave()
    entries=[]
    for name in STATS:
        entry=unreal.PTKEnemySpawnEntry();entry.set_editor_property('enemy_class',CLASSES[name]);entry.set_editor_property('count',1);entries.append(entry)
    spawner.set_editor_property('additional_enemies',entries);spawner.set_editor_property('ring_radius',100.)
    for cls in CLASSES.values():unreal.get_default_object(cls).set_editor_property('initial_attack_delay',100.)
    move(spawner,origin-right*400);spawner.spawn_wave()
    for cls in CLASSES.values():unreal.get_default_object(cls).set_editor_property('initial_attack_delay',.4)
    enemies=actors(unreal.PTKEnemyCharacter)
    yield .2
    check('all_types_target_living_guard',all(e.get_target()==guards[0] for e in enemies))
    health(guards[0]).apply_damage(100000,enemies[0]);yield .2
    check('all_types_retarget_after_death',all(e.get_target()==guards[1] for e in enemies))
    for g in guards[1:]:health(g).apply_damage(100000,enemies[0])
    yield .3
    check('all_guards_dead_target_king',all(e.get_target()==king for e in enemies))
    # King remains a hittable shared combat target.
    for name,(_,damage,_,_) in STATS.items():
        e=spawn(name,king.get_actor_location()-origin-right*45)
        before=hp(king);yield 1.1
        check(name+'_damages_king',hp(king)<before,before-hp(king))


def finish():
    (OUT/'enemy_roster_results.json').write_text(json.dumps(results,indent=2))
    unreal.unregister_slate_post_tick_callback(callback)
    level.editor_request_end_play()
    unreal.SystemLibrary.quit_editor()


sequence=run()
def tick(delta):
    global deadline
    try:
        if time.monotonic()-started>180:raise RuntimeError('Runtime test timed out')
        if time.monotonic()<deadline:return
        deadline=time.monotonic()+next(sequence)
    except StopIteration:finish()
    except Exception:
        check('exception',False,traceback.format_exc());finish()


callback=unreal.register_slate_post_tick_callback(tick)
