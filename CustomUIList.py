# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "object-pointer-uilist-dev",
    "description": "",
    "author": "p2or",
    "version": (0, 1),
    "blender": (2, 79, 0),
    "location": "Text Editor",
    "warning": "", # used for warning icon and text in addons panel
    "wiki_url": "",
    "tracker_url": "",
    "category": "Development"
}

import bpy

from bpy.props import (IntProperty,
                       BoolProperty,
                       StringProperty,
                       CollectionProperty,
                       PointerProperty)

from bpy.types import (Operator,
                       Panel,
                       PropertyGroup,
                       UIList)

# -------------------------------------------------------------------
#   Operators
# -------------------------------------------------------------------

class CUSTOM_OT_actions(Operator):
    """Move items up and down, add and remove"""
    bl_idname = "custom.list_action"
    bl_label = "List Actions"
    bl_description = "Move items up and down, add and remove"
    bl_options = {'REGISTER'}
    
    action = bpy.props.EnumProperty(
        items=(
            ('UP', "Up", ""),
            ('DOWN', "Down", ""),
            ('REMOVE', "Remove", ""),
            ('ADD', "Add", "")))

    def invoke(self, context, event):
        scn = context.scene
        idx = scn.custom_index

        try:
            item = scn.custom[idx]
        except IndexError:
            pass
        else:
            if self.action == 'DOWN' and idx < len(scn.custom) - 1:
                item_next = scn.custom[idx+1].name
                scn.custom.move(idx, idx+1)
                scn.custom_index += 1
                info = 'Item "%s" moved to position %d' % (item.name, scn.custom_index + 1)
                self.report({'INFO'}, info)

            elif self.action == 'UP' and idx >= 1:
                item_prev = scn.custom[idx-1].name
                scn.custom.move(idx, idx-1)
                scn.custom_index -= 1
                info = 'Item "%s" moved to position %d' % (item.name, scn.custom_index + 1)
                self.report({'INFO'}, info)

            elif self.action == 'REMOVE':
                info = 'Item "%s" removed from list' % (scn.custom[idx].name)
                scn.custom_index -= 1
                scn.custom.remove(idx)
                self.report({'INFO'}, info)
                
        if self.action == 'ADD':
            if context.object:
                item = scn.custom.add()
                item.name = context.object.name
                item.obj = context.object
                scn.custom_index = len(scn.custom)-1
                info = '"%s" added to list' % (item.name)
                self.report({'INFO'}, info)
            else:
                self.report({'INFO'}, "Nothing selected in the Viewport")
        return {"FINISHED"}
    

class CUSTOM_OT_addViewportSelection(Operator):
    """Add all items currently selected in the viewport"""
    bl_idname = "custom.add_viewport_selection"
    bl_label = "Add Viewport Selection to List"
    bl_description = "Add all items currently selected in the viewport"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scn = context.scene
        selected_bones = context.selected_bones
        if selected_bones:
            new_bones = []
            for i in selected_bones:
                item = scn.custom.add()
                item.sBoneName = i.name
                new_bones.append(item.sBoneName)
            info = ', '.join(map(str, new_bones))
            self.report({'INFO'}, 'Added: "%s"' % (info))
        else:
            self.report({'INFO'}, "Nothing selected in the Viewport")
        return{'FINISHED'}
    
    
class CUSTOM_OT_printItems(Operator):
    """Print all items and their properties to the console"""
    bl_idname = "custom.print_items"
    bl_label = "Print Items to Console"
    bl_description = "Print all items and their properties to the console"
    bl_options = {'REGISTER', 'UNDO'}
    
    reverse_order = BoolProperty(
        default=False,
        name="Reverse Order")
    
    @classmethod
    def poll(cls, context):
        return bool(context.scene.custom)
    
    def execute(self, context):
        scn = context.scene
        if self.reverse_order:
            for i in range(scn.custom_index, -1, -1):        
                ob = scn.custom[i].obj
                print ("Object:", ob,"-",ob.name, ob.type)
        else:
            for item in scn.custom:
                ob = item.obj
                print ("Object:", ob,"-",ob.name, ob.type)
        return{'FINISHED'}


class CUSTOM_OT_clearList(Operator):
    """Clear all items of the list"""
    bl_idname = "custom.clear_list"
    bl_label = "Clear List"
    bl_description = "Clear all items of the list"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.custom)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
        
    def execute(self, context):
        if bool(context.scene.custom):
            context.scene.custom.clear()
            self.report({'INFO'}, "All items removed")
        else:
            self.report({'INFO'}, "Nothing to remove")
        return{'FINISHED'}
    
    
class CUSTOM_OT_removeDuplicates(Operator):
    """Remove all duplicates"""
    bl_idname = "custom.remove_duplicates"
    bl_label = "Remove Duplicates"
    bl_description = "Remove all duplicates"
    bl_options = {'INTERNAL'}

    def find_duplicates(self, context):
        """find all duplicates by name"""
        name_lookup = {}
        for c, i in enumerate(context.scene.custom):
            name_lookup.setdefault(i.obj.name, []).append(c)
        duplicates = set()
        for name, indices in name_lookup.items():
            for i in indices[1:]:
                duplicates.add(i)
        return sorted(list(duplicates))
        
    @classmethod
    def poll(cls, context):
        return bool(context.scene.custom)
        
    def execute(self, context):
        scn = context.scene
        removed_items = []
        # Reverse the list before removing the items
        for i in self.find_duplicates(context)[::-1]:
            scn.custom.remove(i)
            removed_items.append(i)
        if removed_items:
            scn.custom_index = len(scn.custom)-1
            info = ', '.join(map(str, removed_items))
            self.report({'INFO'}, "Removed indices: %s" % (info))
        else:
            self.report({'INFO'}, "No duplicates")
        return{'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
    
    
class CUSTOM_OT_selectItems(Operator):
    """Select Items in the Viewport"""
    bl_idname = "custom.select_items"
    bl_label = "Select Item(s) in Viewport"
    bl_description = "Select Items in the Viewport"
    bl_options = {'REGISTER', 'UNDO'}

    select_all = BoolProperty(
        default=False,
        name="Select all Items of List",
        options={'SKIP_SAVE'})
        
    @classmethod
    def poll(cls, context):
        return bool(context.scene.custom)
    
    def execute(self, context):
        scn = context.scene
        idx = scn.custom_index
        
        try:
            item = scn.custom[idx]
        except IndexError:
            self.report({'INFO'}, "Nothing selected in the list")
            return{'CANCELLED'}
                   
        obj_error = False
        bpy.ops.object.select_all(action='DESELECT')
        if not self.select_all:
            name = scn.custom[idx].obj.name
            obj = scn.objects.get(name, None)
            if not obj: 
                obj_error = True
            else:
                obj.select = True
                info = '"%s" selected in Vieport' % (obj.name)
        else:
            selected_items = []
            unique_objs = set([i.obj.name for i in scn.custom])
            for i in unique_objs:
                obj = scn.objects.get(i, None)
                if obj:
                    obj.select = True
                    selected_items.append(obj.name)
            
            if not selected_items: 
                obj_error = True
            else:
                missing_items = unique_objs.difference(selected_items)
                if not missing_items:
                    info = '"%s" selected in Viewport' \
                        % (', '.join(map(str, selected_items)))
                else:
                    info = 'Missing items: "%s"' \
                        % (', '.join(map(str, missing_items)))
        if obj_error: 
            info = "Nothing to select, object removed from scene"
        self.report({'INFO'}, info)    
        return{'FINISHED'}


# class CUSTOM_OT_deleteObject(Operator):
#     """Delete object from scene"""
#     bl_idname = "custom.delete_object"
#     bl_label = "Remove Object from Scene"
#     bl_description = "Remove object from scene"
#     bl_options = {'REGISTER', 'UNDO'}

#     @classmethod
#     def poll(cls, context):
#         return bool(context.scene.custom)

#     def invoke(self, context, event):
#         return context.window_manager.invoke_confirm(self, event)
        
#     def execute(self, context):
#         scn = context.scene
#         selected_objs = context.selected_objects
#         idx = scn.custom_index
#         try:
#             item = scn.custom[idx]
#         except IndexError:
#             pass
#         else:        
#             ob = scn.objects.get(item.obj.name)
#             if not ob:
#                 self.report({'INFO'}, "No object of that name found in scene")
#                 return {"CANCELLED"}
#             else:
#                 bpy.ops.object.select_all(action='DESELECT')
#                 ob.select = True
#                 bpy.ops.object.delete()
                
#             for i in selected_objs:
#                 i.select = True
                
#             info = 'Item "%s" removed from Scene' % (scn.custom[idx].name)
#             scn.custom_index -= 1
#             scn.custom.remove(idx)
#             self.report({'INFO'}, info)
#         return{'FINISHED'}
    

# -------------------------------------------------------------------
#   Drawing
# -------------------------------------------------------------------

class CUSTOM_UL_items(UIList):
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        obj = item
    #    custom_icon = "OUTLINER_OB_%s" % obj.type
        split = layout.split(0.3)
    #    split.label("Index: %d" % (index))
        split.prop(obj, 'sBoneName', text="", emboss=False, translate=False)
            
    def invoke(self, context, event):
        pass   

class CUSTOM_PT_objectList(Panel):
    """Adds a custom panel to the TEXT_EDITOR"""
    bl_idname = 'TEXT_PT_my_panel'
    bl_space_type = "TEXT_EDITOR"
    bl_region_type = "UI"
    bl_label = "Custom Object List Demo"

    def draw(self, context):
        layout = self.layout
        scn = bpy.context.scene

        rows = 2
        row = layout.row()
        row.template_list("CUSTOM_UL_items", "", scn, "custom", scn, "custom_index", rows=rows)

        col = row.column(align=True)
        col.operator("custom.list_action", icon='ZOOMIN', text="").action = 'ADD'
        col.operator("custom.list_action", icon='ZOOMOUT', text="").action = 'REMOVE'
        col.separator()
        col.operator("custom.list_action", icon='TRIA_UP', text="").action = 'UP'
        col.operator("custom.list_action", icon='TRIA_DOWN', text="").action = 'DOWN'

        row = layout.row()
        col = row.column(align=True)
        row = col.row(align=True)
        row.operator("custom.print_items", icon="LINENUMBERS_ON")
        row = col.row(align=True)
        row.operator("custom.clear_list", icon="X")
        row.operator("custom.remove_duplicates", icon="GHOST")
        
        row = layout.row()
        col = row.column(align=True)
        row = col.row(align=True)
        row.operator("custom.add_viewport_selection", icon="HAND") #LINENUMBERS_OFF, ANIM
        row = col.row(align=True)
#        row.operator("custom.select_items", icon="VIEW3D", text="Select Item in 3D View")
#        row.operator("custom.select_items", icon="GROUP", text="Select All Items in 3D View").select_all = True
        row = col.row(align=True)
        # row.operator("custom.delete_object", icon="X")


# -------------------------------------------------------------------
#   Collection
# -------------------------------------------------------------------

class FTressFXBoneProps(bpy.types.PropertyGroup):
    
    @classmethod
    def register(FTressFXBoneProps):
        print('here')
        FTressFXBoneProps.sBoneName = bpy.props.StringProperty(
            name="Bone Name", 
            description="Bone Name"
        )

        # bpy.types.Object.TressFXBoneProp = bpy.props.PointerProperty(
        #     type=FTressFXBoneProps, 
        #     name="TressFX Bone Property", 
        #     description="TressFX bone Properties"
        # )
   

# -------------------------------------------------------------------
#   Register & Unregister
# -------------------------------------------------------------------

classes = (
    FTressFXBoneProps,
    CUSTOM_OT_actions,
    CUSTOM_OT_addViewportSelection,
    CUSTOM_OT_printItems,
    CUSTOM_OT_clearList,
    CUSTOM_OT_removeDuplicates,
    CUSTOM_OT_selectItems,
#    CUSTOM_OT_deleteObject,
    CUSTOM_UL_items,
    CUSTOM_PT_objectList
)

def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)
    
    # Custom scene properties
    bpy.types.Scene.custom = CollectionProperty(type=FTressFXBoneProps)
    bpy.types.Scene.custom_index = IntProperty()
    

def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
    
    del bpy.types.Scene.custom
    del bpy.types.Scene.custom_index


if __name__ == "__main__":
    register()