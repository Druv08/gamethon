"""Import four enemies into the existing project. Run via Unreal Python commandlet.

Only the four new enemy asset directories and existing development spawner's
additional entries are updated. Swarm Node, guards, King and start flow stay intact.
"""
import json
from pathlib import Path
import unreal

ROOT=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
STATS={'Infiltrator':(120.,20.,280.,1.25),'Hijacker':(180.,25.,230.,1.5),
       'Encrypter':(350.,35.,150.,1.),'Exfiltrator':(160.,20.,190.,5.)}
DIRS=['Down','Up','Left','Right']
LIB=unreal.EditorAssetLibrary
ASSETS=unreal.AssetToolsHelpers.get_asset_tools()


def save(obj):
    assert obj is not None
    assert LIB.save_loaded_asset(obj,only_if_is_dirty=False),obj.get_name()


def asset(name,path,cls,factory):
    LIB.make_directory(path)
    obj=LIB.load_asset(path+'/'+name) if LIB.does_asset_exist(path+'/'+name) else None
    return obj or ASSETS.create_asset(name,path,cls,factory)


def directional(books,anim):
    value=unreal.PTKDirectionalFlipbooks()
    for d in DIRS:value.set_editor_property(d.lower(),books[anim+'_'+d])
    return value


def blueprint(name,path,parent):
    factory=unreal.BlueprintFactory();factory.set_editor_property('parent_class',parent)
    bp=asset(name,path,unreal.Blueprint,factory)
    return bp,unreal.get_default_object(bp.generated_class())


def generate(name,stats):
    source=ROOT/'ArtSource/Characters/Enemies'/name
    manifest=json.loads((source/'manifest.json').read_text())
    root='/Game/PTK/Characters/Enemies/'+name
    tasks=[]
    for frame in manifest['frames']:
        task=unreal.AssetImportTask()
        for key,value in dict(filename=str(source/'Frames'/frame['folder']/(frame['stem']+'.png')),
                              destination_path=root+'/Textures',destination_name='T_'+name+'_'+frame['stem'],
                              automated=True,replace_existing=True,save=True).items():task.set_editor_property(key,value)
        tasks.append(task)
    ASSETS.import_asset_tasks(tasks)
    sprites={}
    for frame in manifest['frames']:
        stem=frame['stem']
        texture=LIB.load_asset(root+'/Textures/T_'+name+'_'+stem)
        for key,value in dict(filter=unreal.TextureFilter.TF_NEAREST,
                              mip_gen_settings=unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS,
                              compression_settings=unreal.TextureCompressionSettings.TC_EDITOR_ICON,
                              srgb=True,never_stream=True,lod_group=unreal.TextureGroup.TEXTUREGROUP_PIXELS2D).items():
            texture.set_editor_property(key,value)
        save(texture)
        sprite=asset('SPR_'+name+'_'+stem,root+'/Sprites',unreal.PaperSprite,unreal.PaperSpriteFactory())
        for key,value in dict(source_texture=texture,source_uv=unreal.Vector2D(0,0),
                              source_dimension=unreal.Vector2D(*frame.get('canvas',manifest['canvas'])),
                              pixels_per_unreal_unit=1.,pivot_mode=unreal.SpritePivotMode.CUSTOM,
                              custom_pivot_point=unreal.Vector2D(*frame.get('pivot',manifest['pivot'])),
                              snap_pivot_to_pixel_grid=True,sprite_collision_domain=unreal.SpriteCollisionMode.NONE).items():
            sprite.set_editor_property(key,value)
        save(sprite);sprites[stem]=sprite
    books={}
    def book(stem,keys,fps):
        obj=asset('FB_'+name+'_'+stem,root+'/Flipbooks',unreal.PaperFlipbook,unreal.PaperFlipbookFactory())
        frames=[]
        for key in keys:
            f=unreal.PaperFlipbookKeyFrame();f.set_editor_property('sprite',sprites[key]);f.set_editor_property('frame_run',1);frames.append(f)
        obj.set_editor_property('key_frames',frames);obj.set_editor_property('frames_per_second',fps)
        save(obj);books[stem]=obj
    for d in DIRS:
        book('Idle_'+d,['Idle_'+d],8.)
        for anim,fps in [('Walk',10.),('Attack',12.)]:
            book(anim+'_'+d,[f'{anim}_{d}_{i:02}' for i in range(1,9)],fps)
    book('Death',[f'Death_{i:02}' for i in range(1,9)],9.)
    projectile=None
    if name=='Exfiltrator':
        for d in DIRS:book('Flight_'+d,['Flight_'+d+'_01'],12.)
        book('Impact',['Impact_01'],12.)
        projectile,pcdo=blueprint('BP_Shot_Exfiltrator',root+'/Blueprints',unreal.PTKProjectile)
        for key,value in dict(flight_flipbooks=directional(books,'Flight'),impact_flipbook=books['Impact'],
                              splash_radius=0.,collision_radius=10.,impact_lifetime=.12).items():pcdo.set_editor_property(key,value)
        unreal.BlueprintEditorLibrary.compile_blueprint(projectile);save(projectile)
    bp,cdo=blueprint('BP_'+name,root+'/Blueprints',unreal.PTKEnemyCharacter)
    hp,damage,speed,reach=stats
    for key,value in dict(enemy_id=name,enemy_display_name=unreal.Text(name),max_move_speed=speed,
                          collision_radius=18.,collision_half_height=18.,
                          attack_damage=damage,tile_size=64.,attack_range_tiles=reach,
                          detection_range=1400.,attack_range_tolerance=0.,attack_cooldown=1.2,
                          b_attack_hits_multiple_targets=False,default_facing_direction=unreal.PTKFacingDirection.DOWN,
                          idle_flipbooks=directional(books,'Idle'),walk_flipbooks=directional(books,'Walk'),
                          attack_flipbooks=directional(books,'Attack'),death_flipbook=books['Death']).items():
        # Unreal strips the C++ boolean prefix in its reflected Python name.
        cdo.set_editor_property(key[2:] if key.startswith('b_') else key,value)
    cdo.get_editor_property('health_component').set_editor_property('max_health',hp)
    if projectile:
        cdo.set_editor_property('projectile_class',projectile.generated_class())
        cdo.set_editor_property('projectile_speed',700.)
        cdo.set_editor_property('muzzle_height_offset',55.)
        cdo.set_editor_property('attack_impact_fraction',.5)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp);save(bp)
    assert isinstance(cdo,unreal.PTKEnemyCharacter)
    assert cdo.get_editor_property('attack_damage')==damage
    assert cdo.get_editor_property('health_component').get_editor_property('max_health')==hp
    for anim,count in [('Idle',1),('Walk',8),('Attack',8)]:
        for d in DIRS:assert len(books[anim+'_'+d].get_editor_property('key_frames'))==count
    assert len(books['Death'].get_editor_property('key_frames'))==8
    unreal.log('ROSTER ASSETS PASS | '+name)
    return bp


def main():
    roster={name:generate(name,stats) for name,stats in STATS.items()}
    level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    assert level.load_level('/Game/PTK/Maps/L_PTK_TestGround')
    spawners=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.PTKEnemySpawner)]
    assert len(spawners)==1, 'Expected the existing single development spawner'
    entries=[]
    for name,bp in roster.items():
        entry=unreal.PTKEnemySpawnEntry()
        entry.set_editor_property('enemy_class',bp.generated_class());entry.set_editor_property('count',5)
        entries.append(entry)
    spawners[0].set_editor_property('additional_enemies',entries)
    assert level.save_current_level()
    unreal.log('ROSTER IMPORT PASS | four types, five each; original Swarm settings preserved')


main()
