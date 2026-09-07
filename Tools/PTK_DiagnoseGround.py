"""Diagnostic: why is the battlefield ground not drawing? Editor-only, no PIE."""
import json
import os
import unreal

out = []


def line(text):
    out.append(str(text))
    unreal.log("[GROUND] " + str(text))


level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level.load_level('/Game/PTK/Maps/L_PTK_Battlefield')
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

sprite = unreal.EditorAssetLibrary.load_asset('/Game/PTK/Maps/SPR_Battlefield')
line('sprite asset          : {}'.format(sprite))
if sprite:
    for prop in ('source_texture', 'source_uv', 'source_dimension',
                 'pixels_per_unreal_unit', 'default_material',
                 'alternate_material', 'sprite_collision_domain'):
        try:
            line('  {:<22}: {}'.format(prop, sprite.get_editor_property(prop)))
        except Exception as exc:  # noqa: BLE001
            line('  {:<22}: <{}>'.format(prop, exc))

tex = unreal.EditorAssetLibrary.load_asset('/Game/PTK/Maps/T_PTK_Battlefield')
line('texture               : {}'.format(tex))
if tex:
    for prop in ('blueprint_get_size_x', 'compression_settings', 'srgb', 'lod_group'):
        try:
            line('  {:<22}: {}'.format(prop, tex.get_editor_property(prop)))
        except Exception:  # noqa: BLE001
            pass
    line('  size                  : {} x {}'.format(
        tex.blueprint_get_size_x(), tex.blueprint_get_size_y()))

for actor in actors.get_all_level_actors():
    if actor.get_actor_label() != 'Battlefield_Ground':
        continue
    line('ground actor          : {}'.format(actor.get_actor_label()))
    line('  location              : {}'.format(actor.get_actor_location()))
    line('  scale                 : {}'.format(actor.get_actor_scale3d()))
    line('  hidden                : {}'.format(actor.get_editor_property('hidden')))
    comp = actor.get_editor_property('render_component')
    line('  render component      : {}'.format(comp))
    if comp:
        line('  component sprite      : {}'.format(comp.get_editor_property('source_sprite')))
        line('  visible               : {}'.format(comp.get_editor_property('visible')))
        line('  hidden in game        : {}'.format(comp.get_editor_property('hidden_in_game')))
        line('  translucency priority : {}'.format(
            comp.get_editor_property('translucency_sort_priority')))
        bounds = comp.get_editor_property('bounds') if False else None
        line('  world bounds extent   : {}'.format(
            actor.get_actor_bounds(False)))

path = os.path.join(
    unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()),
    'Tools', '_Output')
os.makedirs(path, exist_ok=True)
with open(os.path.join(path, 'ground_diag.txt'), 'w', encoding='utf-8') as handle:
    handle.write('\n'.join(out) + '\n')
