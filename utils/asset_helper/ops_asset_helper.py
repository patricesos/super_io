import os.path

import bpy
from bpy.props import BoolProperty, StringProperty, EnumProperty, IntProperty

mark_list = []


def redraw_window():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def update_mark_list(self, context):
    global mark_list
    mark_list.clear()

    def mark_obj():
        for obj in context.selected_objects:
            mark_list.append(obj)

    def mark_mat():
        for obj in context.selected_objects:
            for slot in obj.material_slots:
                mat = slot.material
                if mat:
                    if mat not in mark_list:
                        mark_list.append(mat)

    def mark_world():
        for world in bpy.data.worlds:
            mark_list.append(world)

    if self.action == 'OBJECT':
        mark_obj()
    elif self.action == 'MATERIAL':
        mark_mat()
    elif self.action == 'ALL':
        mark_obj()
        mark_mat()
    elif self.action == 'WORLD':
        mark_world()

    redraw_window()


class object_asset(bpy.types.Operator):
    bl_options = {'UNDO_GROUPED'}

    clear = False

    action: EnumProperty(name='Type', items=[
        ('OBJECT', 'Object', '', 'OBJECT_DATA', 0),
        ('MATERIAL', 'Material', '', 'MATERIAL', 1),
        ('ALL', 'Separate', '', 'MATSHADERBALL', 2),
        ('WORLD', 'World', '', 'WORLD', 4),
    ], update=update_mark_list)

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.prop(self, 'action', expand=True)

        col = layout.box().column(align=True)
        if len(mark_list) == 0:
            col.label(text='None')

        for obj in mark_list:
            if isinstance(obj, bpy.types.Object):
                icon = 'OBJECT_DATA'
            elif isinstance(obj, bpy.types.Material):
                icon = 'MATERIAL'
            elif isinstance(obj, bpy.types.World):
                icon = 'WORLD'
            else:
                icon = 'X'
            if self.clear:
                if obj.asset_data is None: continue
                col.label(text=obj.name, icon=icon)
            else:
                col.label(text=obj.name, icon=icon)

    def invoke(self, context, event):
        update_mark_list(self, context)

        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        for obj in mark_list:
            if not self.clear:
                obj.asset_mark()
                obj.asset_generate_preview()
            else:
                obj.asset_clear()

        redraw_window()

        return {"FINISHED"}


class SPIO_OT_mark_object_asset(object_asset, bpy.types.Operator):
    """Mark Selected Objects As Asset"""
    bl_label = 'Mark Selected Objects As Asset'
    bl_idname = 'spio.mark_object_asset'
    clear = False


class SPIO_OT_clear_object_asset(object_asset, bpy.types.Operator):
    """Clear Selected Asset"""
    bl_label = 'Clear Selected Asset'
    bl_idname = 'spio.clear_object_asset'
    clear = True


# code from https://github.com/johnnygizmo/asset_snapshot/blob/main/__init__.py

class SPIO_OT_asset_snap_shot(bpy.types.Operator):
    """Snapshot Active Object"""
    bl_label = 'Snapshot Asset'
    bl_idname = 'spio.asset_snap_shot'

    def snapshot(self, context, ob):
        import random
        import os

        scene = context.scene

        # Save some basic settings
        hold_x = context.scene.render.resolution_x
        hold_y = context.scene.render.resolution_y
        hold_filepath = context.scene.render.filepath

        # Find objects that are hidden in viewport and hide them in render
        tempHidden = []
        for o in bpy.data.objects:
            if o.hide_get() == True:
                o.hide_render = True
                tempHidden.append(o)

        # Change Settings
        context.scene.render.resolution_y = scene.spio_snapshot_resolution
        context.scene.render.resolution_x = scene.spio_snapshot_resolution
        switchback = False
        if bpy.ops.view3d.camera_to_view.poll():
            bpy.ops.view3d.camera_to_view()
            switchback = True

        # Ensure outputfile is set to png (temporarily, at least)
        previousFileFormat = scene.render.image_settings.file_format
        if scene.render.image_settings.file_format != 'PNG':
            scene.render.image_settings.file_format = 'PNG'

        filename = str(random.randint(0, 100000000000)) + ".png"
        filepath = str(os.path.abspath(os.path.join(os.sep, 'tmp', filename)))
        bpy.context.scene.render.filepath = filepath

        # Render File, Mark Asset and Set Image
        bpy.ops.render.opengl(write_still=True)
        ob.asset_mark()
        override = bpy.context.copy()
        override['id'] = ob
        bpy.ops.ed.lib_id_load_custom_preview(override, filepath=filepath)

        # Unhide the objects hidden for the render
        for o in tempHidden:
            o.hide_render = False
        # Reset output file format
        scene.render.image_settings.file_format = previousFileFormat

        # Cleanup
        os.unlink(filepath)
        context.scene.render.resolution_y = hold_y
        context.scene.render.resolution_x = hold_x
        context.scene.render.filepath = hold_filepath
        if switchback:
            bpy.ops.view3d.view_camera()

    def execute(self, context):
        self.snapshot(context, context.active_object)

        redraw_window()

        return {"FINISHED"}


class SPIO_OT_batch_generate_thumbs_from_clipboard(bpy.types.Operator):
    """Generate selected asset' thumbs from clipboard images (match by name)"""
    bl_label = 'Generate Thumbnails from Clipboard Images'
    bl_idname = 'spio.batch_generate_thumbs_from_clipboard'

    match_obj = []
    clipboard = None
    filepaths = None

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) != 0

    def invoke(self, context, event):
        self.match_obj = []
        self.clipboard = None

        from ...clipboard.clipboard import Clipboard
        from ...preferences import get_pref

        self.clipboard = Clipboard()
        filepaths = self.clipboard.pull_files_from_clipboard(force_unicode=get_pref().force_unicode)
        if len(filepaths) == 0:
            return {'CANCELLED'}

        self.filepaths = filepaths

        for obj in context.selected_objects:
            if obj.asset_data:
                self.match_obj.append(obj.name)

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.label(text="Matched objects:")

        for path in self.filepaths:
            basename = os.path.basename(path)
            base, sep, ext = basename.rpartition('.')
            if base == '' and sep == '':
                name = ext  # 若无分隔，ext为名字
            else:
                name = base  # 若有分隔，base为名字

            if name in self.match_obj:
                self.layout.label(text=name, icon='OBJECT_DATA')

    def execute(self, context):
        for path in self.filepaths:
            basename = os.path.basename(path)
            base, sep, ext = basename.rpartition('.')
            if base == '' and sep == '':
                name = ext  # 若无分隔，ext为名字
            else:
                name = base  # 若有分隔，base为名字

            if name in self.match_obj:
                obj = bpy.data.objects[name]
                override = context.copy()
                override['id'] = obj
                bpy.ops.ed.lib_id_load_custom_preview(override, filepath=path)

        redraw_window()

        return {"FINISHED"}


def register():
    bpy.utils.register_class(SPIO_OT_mark_object_asset)
    bpy.utils.register_class(SPIO_OT_clear_object_asset)
    bpy.utils.register_class(SPIO_OT_asset_snap_shot)
    bpy.utils.register_class(SPIO_OT_batch_generate_thumbs_from_clipboard)

    bpy.types.Scene.spio_snapshot_resolution = IntProperty(
        name="Snapshot Resolution",
        description="Resolution to render the preview",
        min=32,
        soft_max=512,
        default=256
    )


def unregister():
    bpy.utils.unregister_class(SPIO_OT_mark_object_asset)
    bpy.utils.unregister_class(SPIO_OT_clear_object_asset)
    bpy.utils.unregister_class(SPIO_OT_asset_snap_shot)
    bpy.utils.unregister_class(SPIO_OT_batch_generate_thumbs_from_clipboard)

    del bpy.types.Scene.spio_snapshot_resolution
