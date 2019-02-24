bl_info = {
    "name": "TressFX Exporter",
    "author": "Kostenick, Jacob",
    "version": (0, 0, 1),
    "blender": (2, 79, 0),
    "description": "YEET",
    "warning": "",
    "wiki_url": "",
    "category": "",
}

import ctypes
import random
import sys
import bpy
import json

#__________________________________________________________________________

def OnTressFXBaseMeshChange(self, context):
    #NOTE: self is FTressFXProps instance
    oWM = context.window_manager
    print("Base Mesh Change")

    if self.sBaseMesh in bpy.data.objects:

        oBaseMesh = bpy.data.objects[self.sBaseMesh]
        if oBaseMesh.type != "MESH":
            self.sBaseMesh = ""
            print("Invalid Mesh selected.")
        else:
            print("new mesh set: " + oBaseMesh.name)
            
            


'''      
# ----------------------------------------
# Property definitions
# ----------------------------------------
'''
   
class FTressFXProps(bpy.types.PropertyGroup):
    
    @classmethod
    def register(FTressFXProps):
        FTressFXProps.sBaseMesh = bpy.props.StringProperty(
            name="Base Mesh", 
            description="The mesh the hairs are attached to",
            update=OnTressFXBaseMeshChange
            )
        bpy.types.Object.TressFXProps = bpy.props.PointerProperty(
            type=FTressFXProps, 
            name="TressFX Properties", 
            description="TressFX Properties"
            )

    @classmethod
    def unregister(cls):
        del bpy.types.Object.TressFXProps


'''      
# ----------------------------------------
# UI
# ----------------------------------------
'''

class FTressFXPanel(bpy.types.Panel):
    bl_label = "TressFX Export"
    bl_idname = "TressFX_Panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'object'

    def draw(self, context):
        layout = self.layout

        oTargetObject = context.active_object
        oWM = context.window_manager
        oTFXProps = oTargetObject.TressFXProps

        MainBox = layout.box()
        MainBox.label(text='TressFX')


        if oTargetObject is not None:

            BaseMeshRow = MainBox.row()
            BaseMeshBox = BaseMeshRow.box()
            split = BaseMeshBox.split(percentage=0.4)            
            LeftCol = split.column()
            LeftCol.label(text="Base Mesh: ")
            RightCol = split.column()
            RightCol.prop_search(oTFXProps, "sBaseMesh",  context.scene, "objects", text="")



class TRESSFX_SomeOperatorTodo(bpy.types.Operator):
    '''
    TODO
    '''    
    bl_idname = "TressFX.todo"
    bl_label = "TressFX: todo"

    @classmethod
    def poll(cls, context):

        #TODO: check if object is bound yet
        return context.active_object is not None


    def execute(self, context):
        
        oTargetObject = context.active_object
        return {'FINISHED'}      


    


def register():
    bpy.utils.register_class(FTressFXPanel)
    bpy.utils.register_class(FTressFXProps)


def unregister():
    bpy.utils.unregister_class(FTressFXPanel)
    bpy.utils.unregister_class(FTressFXProps)

if __name__ == "__main__":
    register()
    
    

