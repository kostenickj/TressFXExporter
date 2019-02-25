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
from bpy_extras.io_utils import ExportHelper
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

def OnTressFXCollisionMeshChange(self, context):
    #NOTE: self is FTressFXProps instance
    oWM = context.window_manager
    print("Collision Mesh Change")

    if self.sCollisionMesh in bpy.data.objects:

        oCollisionMesh = bpy.data.objects[self.sCollisionMesh]
        if oCollisionMesh.type != "MESH":
            self.sCollisionMesh = ""
            print("Invalid collision Mesh selected.")
        else:
            print("new collision mesh set: " + oCollisionMesh.name)
            
            


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
            description="The mesh the hairs are attached and weighted to",
            update=OnTressFXBaseMeshChange
            )

        FTressFXProps.sCollisionMesh = bpy.props.StringProperty(
            name="Collision Mesh", 
            description="Collision Mesh for SDF",
            update=OnTressFXCollisionMeshChange
            )

        FTressFXProps.eNumVertsPerStrand = bpy.props.EnumProperty(
            name='Num Verts Per Strand',
            description='Number of vertices per strand',
            items=[('4', '4', '4'),('8', '8', '8'),('16', '16', '16'),('32', '32', '32')],
            default = '8'
            )

        FTressFXProps.fMinimumCurveLength = bpy.props.FloatProperty(
            name='',
            description='Minimum curve length is to filter out hair shorter than the input length. In some case, it is hard to get rid of short hair using modeling tool. This option will be handy in that case. If it is set to zero, then there will be no filtering. ',
            min = 0,
            soft_min = 0,
            precision = 6
            )

        FTressFXProps.bBothEndsImmovable = bpy.props.BoolProperty(
            name="Both ends immovable", 
            description="makes both ending vertices get zero inverse mass",
            default=False
            )

        FTressFXProps.bInvertZAxis = bpy.props.BoolProperty(
            name="Invert Z-axis of Hairs", 
            description="inverts the Z component of hair vertices. This may be useful to deal with some engines using left-handed coordinate system",
            default=False
            )
        
        FTressFXProps.bInvertYAxisUV = bpy.props.BoolProperty(
            name="Invert Y-axis of UV coordinates", 
            description="inverts Y component of UV coordinates",
            default=False
            )

        FTressFXProps.bRandomizeStrandsForLOD = bpy.props.BoolProperty(
            name="Randomize strands for LOD", 
            description="Randomizes hair strand indices so that LOD can uniformly reduce hair strands",
            default=True
            )

        FTressFXProps.bExportTFX = bpy.props.BoolProperty(
            name="Export .tfx File", 
            description="Exports the hair geometry and vertice data",
            default=True
            )

        FTressFXProps.bExportTFXBone = bpy.props.BoolProperty(
            name="Export .tfxbone File", 
            description="Export bone animation data for the skin mesh, requires base mesh to be set",
            default=False
            )

        FTressFXProps.sOutputDir = bpy.props.StringProperty(
            name="Export Directory", 
            description="The export directory",
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
        MainBox.label(text='Export Settings')

        CollisionBox = layout.box()
        CollisionBox.label(text="Collision (optional, SDF only)")


        if oTargetObject is not None:

            #base mesh selection
            BaseMeshRow = MainBox.row()
            BaseMeshSplit = BaseMeshRow.split(percentage=0.5)            
            LeftCol = BaseMeshSplit.column()
            LeftCol.label(text="Base Mesh: ")
            RightCol = BaseMeshSplit.column()
            RightCol.prop_search(oTFXProps, "sBaseMesh",  context.scene, "objects", text="")

            #num verts selection
            NumVertsPerStrandRow = MainBox.row()
            NumVertsSplit = NumVertsPerStrandRow.split(percentage=0.5)
            LeftCol = NumVertsSplit.column()
            LeftCol.label(text="Num Verts Per Strand:")
            RightCol = NumVertsSplit.column()
            RightCol.prop(oTFXProps, "eNumVertsPerStrand", text="")

            #minimum curve length
            MinLengthRow = MainBox.row()
            MinLengthSplit = MinLengthRow.split(percentage=0.5)
            LeftCol = MinLengthSplit.column()
            LeftCol.label(text="Min Curve Length:")
            RightCol = MinLengthSplit.column()
            RightCol.prop(oTFXProps, "fMinimumCurveLength", text="")

            #Both Ends Immovable
            BothEndsRow = MainBox.row()
            BothEndsSplit = BothEndsRow.split(percentage=0.5)
            LeftCol = BothEndsSplit.column()
            LeftCol.label(text="Both Ends Immovable:")
            RightCol = BothEndsSplit.column()
            RightCol.prop(oTFXProps, "bBothEndsImmovable", text="")

            #Invert z
            InvertZRow = MainBox.row()
            InvertZSplit = InvertZRow.split(percentage=0.5)
            LeftCol = InvertZSplit.column()
            LeftCol.label(text="Invert Z-axis of hairs:")
            RightCol = InvertZSplit.column()
            RightCol.prop(oTFXProps, "bInvertZAxis", text="")

            #Invert Y uv
            InvertYUVRow = MainBox.row()
            InvertYUVSplit = InvertYUVRow.split(percentage=0.5)
            LeftCol = InvertYUVSplit.column()
            LeftCol.label(text="Invert Y-axis of UVs:")
            RightCol = InvertYUVSplit.column()
            RightCol.prop(oTFXProps, "bInvertYAxisUV", text="")

            #randomize strands for lod
            RandomizeStrandsRow = MainBox.row()
            RandomizeStrandsSplit = RandomizeStrandsRow.split(percentage=0.5)
            LeftCol = RandomizeStrandsSplit.column()
            LeftCol.label(text="Randomize Strands For LOD:")
            RightCol = RandomizeStrandsSplit.column()
            RightCol.prop(oTFXProps, "bRandomizeStrandsForLOD", text="")

            #export tfx
            ExportTFXRow = MainBox.row()
            ExportTFXSplit = ExportTFXRow.split(percentage=0.5)
            LeftCol = ExportTFXSplit.column()
            LeftCol.label(text="Export Hair Data (.tfx):")
            RightCol = ExportTFXSplit.column()
            RightCol.prop(oTFXProps, "bExportTFX", text="")

            #export tfxbone
            ExportTFXBoneRow = MainBox.row()
            ExportTFXBoneSplit = ExportTFXBoneRow.split(percentage=0.5)
            LeftCol = ExportTFXBoneSplit.column()
            LeftCol.label(text="Export Bone Data (.tfxbone):")
            RightCol = ExportTFXBoneSplit.column()
            RightCol.prop(oTFXProps, "bExportTFXBone", text="")

            #export path label
            OutputPathRow = MainBox.row()
            OutputPathRow.label(text="Output Path:")

            #export path picker and value
            OutPathPickerRow = MainBox.row()
            OutPathPickerRow.prop(oTFXProps, 'sOutputDir', text='')            
            OutPathPickerRow.operator("tressfx.export_dir", icon="FILE_FOLDER", text="")

            ExportRow = MainBox.row()             
            ExportRow.operator("tressfx.export", text="Export")

            #collision Mesh
            ColMeshRow = CollisionBox.row()
            ColMeshSplit = ColMeshRow.split(percentage=0.5)            
            LeftCol = ColMeshSplit.column()
            LeftCol.label(text="Collision Mesh: ")
            RightCol = ColMeshSplit.column()
            RightCol.prop_search(oTFXProps, "sCollisionMesh",  context.scene, "objects", text="")
            CollisionBox.row()

            ColMeshExportRow = CollisionBox.row()
            ColMeshExportRow.operator("tressfx.exportcollision", text="Export Collision Mesh")



        

class FTressFXCollisionExport(bpy.types.Operator):
    '''
    TODO
    '''    

    #NOTE bl_idname has to be all lowercase :(
    bl_idname = "tressfx.exportcollision"
    bl_label = "TressFX: Export Collision Mesh"

    @classmethod
    def poll(cls, context):

        #TODO: check if object is bound yet
        return context.active_object is not None


    def execute(self, context):
        print("todo")
        print("python version:")
        print(sys.version_info)
        self.report({'WARNING'}, "Not yet implemented!")
        return {'CANCELLED'}
        # oTargetObject = context.active_object
        # return {'FINISHED'}      


class FTressFXExport(bpy.types.Operator):
    '''
    TODO
    '''    

    #NOTE bl_idname has to be all lowercase :(
    bl_idname = "tressfx.export"
    bl_label = "TressFX: Export"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def SaveTFXBinaryFile(self, sFilepath, lCurves, oBaseMesh):
        nNumCurves = len(lCurves)
        #todo

    def execute(self, context):
        oTargetObject = context.active_object
        oTFXProps = oTargetObject.TressFXProps

        #retreive stuff
        print("SETTINGS:")

        nNumVertsPerStrand = None
        oBaseMesh = None

        if oTFXProps.sBaseMesh and oTFXProps.sBaseMesh in bpy.data.objects:
            oBaseMesh = bpy.data.objects[oTFXProps.sBaseMesh]
            print('     Base Mesh: ' + oBaseMesh.name)
        else:
            self.report({'WARNING'}, "Base mesh not found!")
            return {'CANCELLED'}

        if oTFXProps.eNumVertsPerStrand is not None:
            nNumVertsPerStrand = int(oTFXProps.eNumVertsPerStrand)
            print('     nNumVertsPerStrand: ' + str(nNumVertsPerStrand))
        else:
            self.report({'WARNING'}, "Invalid num verts per strand!")
            return {'CANCELLED'}

        fMinCurvelength = oTFXProps.fMinimumCurveLength
        print('     fMinCurvlength: ' + str(fMinCurvelength))
        bBothEndsImmovable = oTFXProps.bBothEndsImmovable
        print('     bBothEndsImmovable: ' + str(bBothEndsImmovable))
        bInvertZAxis = oTFXProps.bInvertZAxis
        print('     bInvertZAxis: ' + str(bInvertZAxis))
        bInvertYAxisUV = oTFXProps.bInvertYAxisUV
        print('     bInvertYAxisUV: ' + str(bInvertYAxisUV))
        bRandomizeStrandsForLOD = oTFXProps.bRandomizeStrandsForLOD
        print('     bRandomizeStrandsForLOD: ' + str(bRandomizeStrandsForLOD))
        bExportTFX = oTFXProps.bExportTFX
        print('     bExportTFX: ' + str(bExportTFX))
        bExportTFXBone = oTFXProps.bExportTFXBone
        print('     bExportTFXBone: ' + str(bExportTFXBone))
        sOutputDir = oTFXProps.sOutputDir
        print('     sOutputDir: ' + str(sOutputDir))

        CurvesList = [] #TODO, actually get curves!
        #TODO option to use curves or particle system, gonna start with particle system only
        CurvesList = oTargetObject.particle_systems[0].particles
        print(CurvesList)
        if bExportTFX:
            self.SaveTFXBinaryFile(sOutputDir, CurvesList, oBaseMesh)

        return {'FINISHED'}      


class FDirectorySelector(bpy.types.Operator, ExportHelper):
    bl_idname = "tressfx.export_dir"
    bl_label = "Ok"
    filename_ext = ""
    filter_folder = bpy.props.BoolProperty(default=True, options={'HIDDEN'})
    bl_options = {'REGISTER'}

    # Define this to tell 'fileselect_add' that we want a directoy
    directory = bpy.props.StringProperty(
        name="Outdir Path",
        description="Exports to this directory"
        )

    def execute(self, context):
        print("Selected dir: '" + self.directory + "'")
        context.active_object.TressFXProps.sOutputDir = self.directory
        return {'FINISHED'}

    def invoke(self, context, event):
        # Open browser, take reference to 'self' read the path to selected
        # file, put path in predetermined self fields.
        # See: https://docs.blender.org/api/current/bpy.types.WindowManager.html#bpy.types.WindowManager.fileselect_add
        context.window_manager.fileselect_add(self)
        # Tells Blender to hang on for the slow user input
        return {'RUNNING_MODAL'}


def register():
    bpy.utils.register_class(FDirectorySelector)
    bpy.utils.register_class(FTressFXExport)
    bpy.utils.register_class(FTressFXCollisionExport)
    bpy.utils.register_class(FTressFXPanel)
    bpy.utils.register_class(FTressFXProps)

def unregister():
    bpy.utils.unregister_class(FDirectorySelector)
    bpy.utils.unregister_class(FTressFXExport)
    bpy.utils.unregister_class(FTressFXCollisionExport)
    bpy.utils.unregister_class(FTressFXPanel)
    bpy.utils.unregister_class(FTressFXProps)


if __name__ == "__main__":
    register()
    
    

