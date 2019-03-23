bl_info = {
    "name": "TressFX Exporter",
    "author": "Kostenick, Jacob",
    "version": (0, 0, 1),
    "blender": (2, 79, 0),
    "description": "YEET",
    "warning": "",
    "wiki_url": "YOLO",
    "category": "Animation",
}

import ctypes
import random
import sys
import os
import bpy
import json
import bmesh
import mathutils
from math import sqrt
from bpy_extras.io_utils import ExportHelper

thisdir = os.path.dirname(__file__)
if not thisdir in sys.path:
    sys.path.append(thisdir )

import Curvesimplifier2 as simp2

# Don't change the following maximum joints per vertex value. It must match the one in TressFX loader and simulation
TRESSFX_MAX_INFLUENTIAL_BONE_COUNT  = 4
TRESSFX_SIM_THREAD_GROUP_SIZE = 64

class TressFX_Float4(ctypes.Structure):
	_fields_ = [('x', ctypes.c_float),
                ('y', ctypes.c_float),
                ('z', ctypes.c_float),
                ('w', ctypes.c_float)]

class TressFX_Float2(ctypes.Structure):
	_fields_ = [('x', ctypes.c_float),
                ('y', ctypes.c_float)]

class BoneweightmapObj:
    weight = 0.0
    boneName= ""
    sourceVertIndex = -1
    # For sorting 
    def __lt__(self, other):
        return self.weight > other.weight

class WeightJointIndexPair:
	weight = 0
	joint_index = -1

	# For sorting 
	def __lt__(self, other):
		return self.weight > other.weight

def FindCurveIntersectionWithMesh(CurveObj, MeshObj):
    """assumes points array goes from root -> tip"""

    CurvePointsAsVectorsArray = [p.co for p in CurveObj.data.splines[0].points]

    #TODO, is this the corret subtraction order to get direction?
    Direction = (CurvePointsAsVectorsArray[1] - CurvePointsAsVectorsArray[0]).normalized()
    #TODO, iterate until i find how many points starting from first point are inside
    # and use direction between the last inside point, and the next point after
    # if only root point is inside mesh, always just use the second point

    for Face in MeshObj.data.polygons:

        Origin = CurvePointsAsVectorsArray[0]
        VerticesIndices = Face.vertices
        p1, p2, p3 = [MeshObj.data.vertices[VerticesIndices[i]].co for i in range(3)]

        #TODO, verts of curve may need to be put in same space as mesh...

        # last arg is clip, which i think should be true but its not finding enough hits...
        found = mathutils.geometry.intersect_ray_tri(p1, p2, p3, Direction, Origin, True)
        #found = mathutils.geometry.intersect_ray_tri(p1, p2, p3, Direction, Origin, False)
        if found is not None:
            return found
    return None


def MoveCurveVertSpaceToBaseMeshSpace(vec, baseMeshObj, CurveObj):
    """needs testing"""
    worldMatrix = CurveObj.matrix_world
    ConvertMatrix = baseMeshObj.convert_space( matrix = worldMatrix, from_space = 'WORLD', to_space = 'LOCAL' )
    NewVert = ConvertMatrix * vec
    return NewVert


def GetNumPointsInsideMesh(MeshObj, CurveObj):
    
    num = 0
    for p in CurveObj.data.splines[0].points:
        inside1 = IsPointInsideMesh(MeshObj, p.co.xyz )
        inside2 = IsPointInsideMesh2(MeshObj, p.co.xyz  )
        # if inside1 != inside2:
        #     raise Exception('inside1 != inside2')
        if inside1 or inside2:
            num = num + 1
    return num

def IsPointInsideMesh(MeshObj, PointInObjectSpace):      
    #direction is irellevant unless mesh is REALLY wierd shaped
    direction = mathutils.Vector((1,0,0))  
    epsilon = direction * 1e-6  
    count = 0  
    result, PointInObjectSpace, normal, index = MeshObj.ray_cast(PointInObjectSpace, direction)  
    while result:  
        count += 1  
        result, PointInObjectSpace, normal, index = MeshObj.ray_cast(PointInObjectSpace + epsilon, direction)  
    return (count % 2) == 1  

#this assumes all faces of the object are pointing outwards
def IsPointInsideMesh2(obj, p, max_dist = 1.84467e+19):

    bResult, point, normal, face = obj.closest_point_on_mesh(p, max_dist)
    p2 = point-p
    v = p2.dot(normal)
    return not(v < 0.0)

def VecDistance(vec1, vec2):
    return sqrt((vec1.x - vec2.x)**2 + (vec1.y - vec2.y)**2 + (vec1.z - vec2.z)**2)

def FindIndexOfClosestVector(Point, VecList):
    closest = VecList[0]
    index = 0
    for i in range (0, len(VecList)):
        if VecDistance(VecList[i], Point) < VecDistance(Point, closest):
            closest = VecList[i]
            index = i
    return index

def FindIndexOfClosestPointOnMesh(vert, Obj):
    objVerts = [v.co for v in Obj.data.vertices]
    index = FindIndexOfClosestVector(vert,objVerts)
    return index

# takes in a curve and subdivides it until it has numpoints >= nDesiredVertNum
def RecursiveSubdivideCurveIfNeeded(context, CurveObj, nDesiredVertNum):
    
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.scene.objects.active = CurveObj

    CurvePoints = [(vert.x, vert.y, vert.z) for vert in [p.co for p in CurveObj.data.splines[0].points]]
    
    if len(CurvePoints) < nDesiredVertNum:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.curve.select_all(action = 'SELECT')
        bpy.ops.curve.subdivide()
        return RecursiveSubdivideCurveIfNeeded(context, CurveObj, nDesiredVertNum)
    else:
        bpy.ops.object.mode_set(mode='OBJECT')
        return CurveObj

def CreateNewCurveFromPoints(StrandVerts, CurveName):
    """strandverts need to be array of mathutils.Vector"""
    curveData = bpy.data.curves.new(CurveName, type='CURVE')
    curveData.dimensions = '3D'
    curveData.resolution_u = 12
    polyline = curveData.splines.new('POLY')
    polyline.points.add(len(StrandVerts) - 1) # theres already one point by default
    
    for i, vert in enumerate(StrandVerts):
        polyline.points[i].co = (vert.x, vert.y, vert.z, 1)

    # create Object
    curveOB = bpy.data.objects.new(CurveName, curveData)
    
    # attach to scene and validate context
    bpy.context.scene.objects.link(curveOB)
    bpy.context.scene.objects.active = curveOB
    curveOB.select = True
    return curveOB

def SeparateCurves(context):
    """this runs out of memory or something on a ton of curves, don't use"""
    active = context.active_object
    splines = active.data.splines
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.curve.select_all(action = 'DESELECT')

    while len(splines) > 1:
        spline = splines[0]
        if spline.bezier_points:
            spline.bezier_points[0].select_control_point = True
        elif spline.points:
            spline.points[0].select = True
        bpy.ops.curve.select_linked()
        bpy.ops.curve.separate()

    bpy.ops.object.mode_set(mode='OBJECT')

def SeparateCurves2(context):
    
    """this is much faster than using the other separatecurves function"""
    Curves = []
    active = context.active_object
    splines = active.data.splines

    for idx, spline in enumerate(splines):        

        CurveName = active.name + "_" + str(idx)
        StrandVerts = [v.co for v in spline.points]
        # create Object
        curveOB = CreateNewCurveFromPoints(StrandVerts, CurveName)
        Curves.append(curveOB)

    #delete original curve that had all the curves in one object
    bpy.ops.object.select_all(action='DESELECT')
    bpy.data.objects[active.name].select = True
    bpy.ops.object.delete()

    return Curves

def OnTressFXBaseMeshChange(self, context):
    #NOTE: self is FTressFXProps instance
    print("Base Mesh Change")

    if self.sBaseMesh in bpy.data.objects:

        oBaseMesh = bpy.data.objects[self.sBaseMesh]
        if oBaseMesh.type != "MESH":
            self.sBaseMesh = ""
            print("Invalid Mesh selected.")
        else:
            print("new mesh set: " + oBaseMesh.name)

def OnBoneSelect(self, context):
    #NOTE: self is FTressFXProps instance
    boneName = self.dummyBoneStr
    if self.sBaseMesh and self.sBaseMesh in bpy.data.objects:
        oBaseMesh = bpy.data.objects[self.sBaseMesh]
        armature = oBaseMesh.parent
        if boneName in armature.data.bones:
            item = self.ExportBones.add()
            item.sBoneName = boneName
    #protect against infinite recursion
    if self.dummyBoneStr != '':
        self.dummyBoneStr = ''

def OnTressFXCollisionMeshChange(self, context):
    #NOTE: self is FTressFXProps instance
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

class TressFXBonesRemoveDuplicates(bpy.types.Operator):
    """Remove all duplicates"""
    bl_idname = "tressfxbones.remove_duplicates"
    bl_label = "Remove Duplicates"
    bl_description = "Remove all duplicates"
    bl_options = {'INTERNAL'}

    def FindDuplicates(self, context):
        """find all duplicates by name"""
        NameLookup = {}

        for c, TressFXBonePropsInstance in enumerate(context.active_object.TressFXProps.ExportBones):
            NameLookup.setdefault(TressFXBonePropsInstance.sBoneName, []).append(c)
        duplicates = set()
        for name, indices in NameLookup.items():
            for i in indices[1:]:
                duplicates.add(i)
        return sorted(list(duplicates))
        
    @classmethod
    def poll(cls, context):
        return bool(context.active_object.TressFXProps)
        
    def execute(self, context):

        OtfxProps = context.active_object.TressFXProps
        RemovedItems = []
        # Reverse the list before removing the items
        for i in self.FindDuplicates(context)[::-1]:
            OtfxProps.ExportBones.remove(i)
            RemovedItems.append(i)
        if RemovedItems:
            OtfxProps.ExportBonesIndex = len(OtfxProps.ExportBones)-1
            info = ', '.join(map(str, RemovedItems))
            self.report({'INFO'}, "Removed indices: %s" % (info))
        else:
            self.report({'INFO'}, "No duplicates")
        return{'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

class TressFXBonesClearList(bpy.types.Operator):
    """Clear all items of the list"""
    bl_idname = "tressfxbones.clear_list"
    bl_label = "Clear List"
    bl_description = "Clear all items of the list"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return bool(context.active_object.TressFXProps)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
        
    def execute(self, context):
        if bool(context.active_object.TressFXProps):
            context.active_object.TressFXProps.ExportBones.clear()
            self.report({'INFO'}, "All items removed")
        else:
            self.report({'INFO'}, "Nothing to remove")
        return{'FINISHED'}


class TressFXBoneListItemsActions(bpy.types.Operator):
    """Move items up and down, add and remove"""
    bl_idname = "tressfxbones.list_action"
    bl_label = "List Actions"
    bl_description = "Move items up and down, and remove"
    bl_options = {'REGISTER'}
    
    action = bpy.props.EnumProperty(
        items=(
            ('UP', "Up", ""),
            ('DOWN', "Down", ""),
            ('REMOVE', "Remove", "")
            )
        )

    def invoke(self, context, event):

        oTfxProps = context.active_object.TressFXProps
        idx = oTfxProps.ExportBonesIndex

        try:
            item = oTfxProps.ExportBones[idx]
        except IndexError:
            pass
        else:
            if self.action == 'DOWN' and idx < len(oTfxProps.ExportBones) - 1:
                item_next = oTfxProps.ExportBones[idx+1].sBoneName
                oTfxProps.ExportBones.move(idx, idx+1)
                oTfxProps.ExportBonesIndex += 1
                info = 'Item "%s" moved to position %d' % (item.sBoneName, oTfxProps.ExportBonesIndex + 1)
                self.report({'INFO'}, info)

            elif self.action == 'UP' and idx >= 1:
                item_prev = oTfxProps.ExportBones[idx-1].sBoneName
                oTfxProps.ExportBones.move(idx, idx-1)
                oTfxProps.ExportBonesIndex -= 1
                info = 'Item "%s" moved to position %d' % (item.sBoneName, oTfxProps.ExportBonesIndex + 1)
                self.report({'INFO'}, info)

            elif self.action == 'REMOVE':
                info = 'Item "%s" removed from list' % (oTfxProps.ExportBones[idx].sBoneName)
                oTfxProps.ExportBonesIndex -= 1
                oTfxProps.ExportBones.remove(idx)
                self.report({'INFO'}, info)
                
        return {"FINISHED"}

class TressFXBoneListItems(bpy.types.UIList):
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        obj = item # item is a FTressFXBoneProps instance
        layout.prop(obj, 'sBoneName', text="", emboss=False, translate=False, icon="BONE_DATA")
            
    def invoke(self, context, event):
        pass

class FTressFXBoneProps(bpy.types.PropertyGroup):
    
    @classmethod
    def register(FTressFXBoneProps):
        FTressFXBoneProps.sBoneName = bpy.props.StringProperty(
            name="Bone Name", 
            description="Bone Name"
        )
   
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

        FTressFXProps.eExportType = bpy.props.EnumProperty(
            name='Export Type',
            description='Export method, uses either particle system or selected curves',
            items=[('PARTICLE_SYSTEM', 'PARTICLE_SYSTEM', 'PARTICLE_SYSTEM'),('CURVES', 'CURVES', 'CURVES')],
            default = 'PARTICLE_SYSTEM'
            )

        FTressFXProps.eBoneExportMode = bpy.props.EnumProperty(
            name='Bone Export Mode',
            description='ALL_WITH_WEIGHT: exports all found bones that have weight. Blacklist: ignore these bones. Whitelist: only these bones ',
            items=[
                ('ALL_WITH_WEIGHT', 'ALL_WITH_WEIGHT', 'ALL_WITH_WEIGHT'),
                ('BLACKLIST', 'BLACKLIST', 'BLACKLIST'),
                ('WHITELIST', 'WHITELIST', 'WHITELIST')
            ],
            default = 'ALL_WITH_WEIGHT'
            )

        FTressFXProps.eNumVertsPerStrand = bpy.props.EnumProperty(
            name='Num Verts Per Strand',
            description='Number of vertices per strand',
            items=[('4', '4', '4'),('8', '8', '8'),('16', '16', '16'),('32', '32', '32')],
            default = '8'
            )

        FTressFXProps.fMinimumCurveLength = bpy.props.FloatProperty(
            name='Mininum Curve length in blender units',
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

        FTressFXProps.bDebugMode = bpy.props.BoolProperty(
            name="Debug Mode", 
            description="Adds extra fields to the file to aid in debugging",
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

        FTressFXProps.sOutputDir = bpy.props.StringProperty(
            name="Export Directory", 
            description="The export directory",
            )
        
        FTressFXProps.sOutputName = bpy.props.StringProperty(
            name="Export File Name", 
            description="The export filename without extension",
            )

        FTressFXProps.sParticleSystem = bpy.props.StringProperty(
            name="Particle System", 
            description="The particle system to export if export method is 'PARTICLE_SYSTEM'",
            )

        FTressFXProps.dummyBoneStr = bpy.props.StringProperty(
            name="Select Bone", 
            description="Select a bone to add",
            update = OnBoneSelect
            )

        FTressFXProps.ExportBones = bpy.props.CollectionProperty( type= FTressFXBoneProps)
        FTressFXProps.ExportBonesIndex = bpy.props.IntProperty()

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

    @classmethod
    def poll(cls, context):
        return context.active_object is not None 


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

            #export type, particle system or selected curves
            ExportTypeRow = MainBox.row()
            ExportTypeSplit = ExportTypeRow.split(percentage=0.5)
            LeftCol = ExportTypeSplit.column()
            LeftCol.label(text="Export Type")
            RightCol = ExportTypeSplit.column()
            RightCol.prop(oTFXProps, "eExportType", text="")

            if oTFXProps.eExportType is not None and oTFXProps.eExportType == 'PARTICLE_SYSTEM':
                ParticleSystemRow = MainBox.row()
                ParticlesystemSplit = ParticleSystemRow.split(percentage=0.5)
                LeftCol = ParticlesystemSplit.column()
                LeftCol.label(text="Partcle System")
                RightCol = ParticlesystemSplit.column()
                RightCol.prop_search(oTFXProps, "sParticleSystem", oTargetObject,"particle_systems", text="")

            BoneExportTypeRow = MainBox.row()
            BoneExportTypeSplit = BoneExportTypeRow.split(percentage=0.5)
            LeftCol = BoneExportTypeSplit.column()
            LeftCol.label(text="Bone Mode")
            RightCol = BoneExportTypeSplit.column()
            RightCol.prop(oTFXProps, "eBoneExportMode", text="")


            if oTFXProps.eBoneExportMode != 'ALL_WITH_WEIGHT' and oTargetObject.parent is not None and oTargetObject.parent.type == 'ARMATURE':
                
                #bone picker
                BonePickerRow = MainBox.row()
                BonePickersplit = BonePickerRow.split(percentage=0.5)
                BonePickerLabel = BonePickersplit.column()
                BonePickerLabel.label(text="Pick bones")
                BonePickerDrop = BonePickersplit.column()
                BonePickerDrop.prop_search(oTFXProps, "dummyBoneStr", oTargetObject.parent.data ,"bones", text="")
                
                #bone list display
                BoneListRow = MainBox.row()
                BoneListRow.template_list("TressFXBoneListItems", "", oTFXProps, "ExportBones", oTFXProps, "ExportBonesIndex", rows=2)
                col = BoneListRow.column(align=True)
                col.operator("tressfxbones.list_action", icon='ZOOMOUT', text="").action = 'REMOVE'
                col.separator()
                col.operator("tressfxbones.list_action", icon='TRIA_UP', text="").action = 'UP'
                col.operator("tressfxbones.list_action", icon='TRIA_DOWN', text="").action = 'DOWN'
                
                #clear and remove dupes buttons
                SpecialRow = MainBox.row()
                SpecialSplit = SpecialRow.split(percentage=0.5)
                leftcol = SpecialSplit.column()
                rightcol = SpecialSplit.column()
                leftcol.operator("tressfxbones.clear_list", icon="X")
                leftcol.operator("tressfxbones.remove_duplicates", icon="GHOST")

                
            #bDebugMode
            DebugModeRow = MainBox.row()
            DebugModeSplit = DebugModeRow.split(percentage=0.5)
            LeftCol = DebugModeSplit.column()
            LeftCol.label(text="Debug Mode")
            RightCol = DebugModeSplit.column()
            RightCol.prop(oTFXProps, "bDebugMode", text="")

            #export path label
            OutputPathRow = MainBox.row()
            OutputPathRow.label(text="Output Path:")

            #export path picker and value
            OutPathPickerRow = MainBox.row()
            OutPathPickerRow.prop(oTFXProps, 'sOutputDir', text='')            
            OutPathPickerRow.operator("tressfx.export_dir", icon="FILE_FOLDER", text="")

            #filename label
            FileNameRow = MainBox.row()
            FileNameRow.label(text="File name (without extension):")
            
            FilenameBoxRow = MainBox.row()
            FilenameBoxRow.prop(oTFXProps, 'sOutputName', text='')    

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
    Exports TressFX Files.
    Requirements:
    1. Base Mesh must be all triangles.
    2. All curves and the base mesh must have rot and scale applied and origin be at the global origin (same space)
    Assumes that the selected UV map on the base mesh is the one to use when generating UV's for the hairs.
    '''    

    #NOTE bl_idname has to be all lowercase :(
    bl_idname = "tressfx.export"
    bl_label = "TressFX: Export"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def GetCurveLength(self, context, curveObj):

        curvePoints = [p.co for p in curveObj.data.splines[0].points]
        length = 0

        for x in range( (len(curvePoints) - 1)):
            vert0 = curvePoints[x]
            vert1 = curvePoints[x + 1]
            length += (vert0-vert1).length
        return length

    def SaveTFXHairJsonFile(self, context, lHairs):

        curvesToUse = []

        # account for minnum curve length
        checkForMinCurveLength = bool(self.fMinCurvelength > 0)

        if checkForMinCurveLength:

            for idx, curve in enumerate(lHairs):
                CurveLength = self.GetCurveLength(context, curve)
                CurveLength_lengthFormatted = '{:.6f}'.format(CurveLength)
                if CurveLength >= self.fMinCurvelength:
                    curvesToUse.append(curve)
                    print('curve idx ' + str(idx) + ' length: ' + CurveLength_lengthFormatted)
                else:
                    print('dicarding curve with index ' + str(idx) + ' length: ' + CurveLength_lengthFormatted) 
        else:
            curvesToUse = lHairs

        if self.bRandomizeStrandsForLOD and not self.bDebugMode:
            random.shuffle(curvesToUse)

        FinalCurves = []
        # num verts per strand is always even so this is fine
        CutoffPoint = int(self.nNumVertsPerStrand / 2)

        TotalNumInside = 0
        
        #make curves compatible with TressFX
        for idx, CurveObj in enumerate(curvesToUse):

            #we need to subdivide the curve if it has less points than self.nNumVertsPerStrand
            CorrectCurve = RecursiveSubdivideCurveIfNeeded(context, CurveObj, self.nNumVertsPerStrand)
            NewCurve = None
            #now resample to exactly nNumVertsPerStrand if needed
            if len(CorrectCurve.data.splines[0].points) != self.nNumVertsPerStrand:

                if self.bDebugMode:
                    print('strand index ' + str(idx) + ' has ' + str(len(CorrectCurve.data.splines[0].points)) + ' points. Simplifying to ' + str(self.nNumVertsPerStrand) )
                
                #modify curve so it has exactly the right number of points
                NewCurve = simp2.SimplifyCurve(context, CorrectCurve, self.nNumVertsPerStrand)
            else:
                NewCurve = CorrectCurve

            if len(NewCurve.data.splines[0].points) != self.nNumVertsPerStrand:
                raise Exception('len(NewCurve.data.splines[0].points) != self.nNumVertsPerStrand')

            #check to see if more than half the points are inside the mesh, if so, discard that strand
            #TODO i think this isnt working right
            NumInside = GetNumPointsInsideMesh(self.oBaseMesh, NewCurve)

            if NumInside > CutoffPoint:
                TotalNumInside = TotalNumInside + 1
                if self.bDebugMode:
                    print('discarding strand with index: ' + str(idx) + '. More than half of the vertices are inside the base mesh.')
                continue
            else:
                FinalCurves.append(NewCurve)
        #enumerate(curvesToUse): end

        nNumCurves = len(FinalCurves)

        if nNumCurves < TRESSFX_SIM_THREAD_GROUP_SIZE:
            if checkForMinCurveLength:
                self.report({'ERROR'}, "Not enough curves found after accounting for Min Curve Length! At least " + str(TRESSFX_SIM_THREAD_GROUP_SIZE) + " curves are required!")
            else:
                self.report({'ERROR'}, "Not enough curves found! At least " + str(TRESSFX_SIM_THREAD_GROUP_SIZE) + " curves are required!")
            return 'ERROR'
        
        OutFilePath = self.sOutputDir + (self.sOutputName if len(self.sOutputName) > 0 else self.oBaseMesh.name)  + ".tfxjson"
        print(OutFilePath)

        FinalObj = {}
        FinalObj['positions'] = []
        FinalObj['uvs'] = []
        FinalObj['numHairStrands'] = nNumCurves
        FinalObj['numVerticesPerStrand'] = self.nNumVertsPerStrand
        if self.bDebugMode:
            FinalObj['totalNumInside'] = TotalNumInside

        for nHairIdx, CurveObj in enumerate(FinalCurves):

            # now we ready to write the points
            strandVerts = []
            CurvePoints = [p.co for p in CurveObj.data.splines[0].points]
            for PtIdx, Point in enumerate(CurvePoints):

                p = TressFX_Float4()
                p.x = Point[0]

                if self.bInvertZAxis:
                    p.z = -Point[2] # flip in z-axis
                else:
                    p.z = Point[2]
                    
                if self.bInvertYAxisUV:
                    p.y = -Point[1]
                else:
                    p.y = Point[1]

                # w component is an inverse mass
                if PtIdx == 0 or PtIdx == 1: # the first two vertices are immovable always. 
                    p.w = 0
                else:
                    p.w = 1.0
                vert = {}
                vert['x'] = p.x
                vert['y'] = p.y
                vert['z'] = p.z
                vert['w'] = p.w
                strandVerts.append(vert)
            # enumerate(CurvePoints):
            FinalObj['positions'].append(strandVerts)
        # enumerate(FinalCurves) END
        
        # get strand texture coords
        for strandIndex, CurveObj in enumerate(FinalCurves):
            
            Points = [p.co for p in CurveObj.data.splines[0].points]
            rootPoint = Points[0]
            pVector = mathutils.Vector((rootPoint[0],rootPoint[1],rootPoint[2]))

            #get closest point on base mesh
            bResult, Location, Normal, FaceIndex = self.oBaseMesh.closest_point_on_mesh(pVector)
            
            #calculate uv at that point on the mesh
            # https://blender.stackexchange.com/questions/79236/access-color-of-a-point-given-the-3d-position-on-the-surface-of-a-polygon
            VerticesIndices = self.oBaseMesh.data.polygons[FaceIndex].vertices
            p1, p2, p3 = [self.oBaseMesh.data.vertices[VerticesIndices[i]].co for i in range(3)]
            UVMapIndices = self.oBaseMesh.data.polygons[FaceIndex].loop_indices
            # always assume the active layer is the one to use
            ActiveUVMap = self.oBaseMesh.data.uv_layers.active
            UV1, UV2, UV3 = [ActiveUVMap.data[UVMapIndices[i]].uv for i in range(3)]
            
            #make them 3d so we can use barycentric_transform
            UV1 = mathutils.Vector((UV1.x, UV1.y,1))
            UV2 = mathutils.Vector((UV2.x, UV2.y,1))
            UV3 = mathutils.Vector((UV3.x, UV3.y,1))

            UVAtPoint = mathutils.geometry.barycentric_transform( Location, p1, p2, p3, UV1, UV2, UV3 )

            UVCoord = TressFX_Float2()
            UVCoord.x = UVAtPoint.x
            UVCoord.y = UVAtPoint.y
            if self.bInvertYAxisUV:
                UVCoord.y = 1.0 - UVCoord.y; # DirectX has it inverted
            
            uvObj = {}
            uvObj['x'] = UVCoord.x
            uvObj['y'] = UVCoord.y
            FinalObj['uvs'].append(uvObj)
        #enumerate(FinalCurves) END

        boneData = self.getTFXBoneJSON(context, FinalCurves)
        if boneData != 'ERROR':
            FinalObj['tfxBoneData'] = boneData
        else:
            return 'ERROR'

        with open(OutFilePath, "w") as TfxFile :
            TfxFile.write(json.dumps(FinalObj, indent=4))
        return FinalCurves

    def getTFXBoneJSON(self, context, Finalcurves):

        VertexGroupNames = [g.name for g in self.oBaseMesh.vertex_groups]
        AllBonesArray = [] # aka used bones
        BonesArray_WithWeightsOnly = []
        FinalObj = {}
        FinalObj['skinningData'] = []

        Armature = self.oBaseMesh.parent

        ExportBonesNames = [j.sBoneName for j in self.ExportBones]

        for bn in Armature.data.bones:
            if bn.name in VertexGroupNames:
                if self.eBoneExportMode == 'WHITELIST':
                    if bn.name in ExportBonesNames:
                        if bn.use_deform:
                            AllBonesArray.append(bn)
                elif self.eBoneExportMode == 'BLACKLIST':
                    if bn.name not in ExportBonesNames:
                        if bn.use_deform:
                            AllBonesArray.append(bn)
                else:
                    if bn.use_deform:
                        AllBonesArray.append(bn) # must be ALL_WITH_WEIGHT

        TotalIntersects = 0
        for RootIndex, CurveObj in enumerate(Finalcurves):

            StrandPoints = [p.co for p in CurveObj.data.splines[0].points]
            #TODO: root point may not always be the first point, especially if the curves were imported from a file
            RootPoint = StrandPoints[0]

            #IntersectionPoint = FindCurveIntersectionWithMesh(CurveObj, self.oBaseMesh)
            IntersectionPoint = RootPoint

            IntersectionPointInWs = CurveObj.matrix_world * IntersectionPoint
            IntersectionPointInOS = self.oBaseMesh.matrix_world.inverted() * IntersectionPointInWs

            if IntersectionPoint is None:
                if self.bDebugMode:
                    print('no intersection point found for Rootindex: ' + str(RootIndex) + ' using rootpoint instead')
                IntersectionPoint = RootPoint
            else:
                TotalIntersects = TotalIntersects + 1

            # #TODO: root points could be well inside the mesh,
            # # and closest_point_on_mesh would return wrong in this case.
            # # use raycast, first point as origin, second point as direction
            # # if it returns nothing then use the root point

            pVector = mathutils.Vector((IntersectionPointInOS[0],IntersectionPointInOS[1],IntersectionPointInOS[2]))

	        # Find the closest point info
            bResult, Location, Normal, FaceIndex = self.oBaseMesh.closest_point_on_mesh(pVector)

            # find closest vertex to location
            FaceObj = self.oBaseMesh.data.polygons[FaceIndex]
            FaceVertices = [self.oBaseMesh.data.vertices[i] for i in FaceObj.vertices]
            ClosestVertIndex = FindIndexOfClosestVector(Location, [F.co for F in FaceVertices])
            ClosestVert = FaceVertices[ClosestVertIndex]

            ClosestVertWeights = []

            for Bone in AllBonesArray:
                weight = -1
                try:
                    weight = self.oBaseMesh.vertex_groups[Bone.name].weight(ClosestVert.index)                    
                except:
                    print('vertex index ' + str(ClosestVert.index) + ' is not weighted to ' + Bone.name )
                    pass

                if weight > 0 :
                    boneweightmapObj = BoneweightmapObj()
                    boneweightmapObj.boneName = Bone.name
                    boneweightmapObj.weight = weight
                    boneweightmapObj.sourceVertIndex = ClosestVert.index
                    ClosestVertWeights.append( boneweightmapObj )
                    if Bone.name not in BonesArray_WithWeightsOnly:
                        BonesArray_WithWeightsOnly.append(Bone.name)
            
            ClosestVertWeights.sort()

            if len(ClosestVertWeights) < 1:
                self.report({'ERROR'}, "No weights found for at least one root position! Make sure to whitelist or blacklist bones! Or use all with weight.")
                return 'ERROR'
            #make sure we have at least 4
            while len(ClosestVertWeights) < TRESSFX_MAX_INFLUENTIAL_BONE_COUNT :
                ClosestVertWeights.append(BoneweightmapObj())

            print('root index: ' + str(RootIndex))
            for idx in range( TRESSFX_MAX_INFLUENTIAL_BONE_COUNT):
                boneweightmapObj = ClosestVertWeights[idx]
                #print( boneweightmapObj.boneName )
                #print( '    weight: ' + '{:.6f}'.format(boneweightmapObj.weight))
                j = {}
                j['weight'] = boneweightmapObj.weight
                j['boneName'] = boneweightmapObj.boneName
                if self.bDebugMode:
                    j['sourceVertIndex'] = boneweightmapObj.sourceVertIndex
                    j['rootIndex'] = RootIndex
                    j['curveName'] = CurveObj.name
                FinalObj['skinningData'].append( j )
        #enumerate(Finalcurves):

        FinalObj['numGuideStrands'] = len(Finalcurves)
        FinalObj['bonesList'] = BonesArray_WithWeightsOnly
        if self.bDebugMode:
            FinalObj['totalIntersects'] = TotalIntersects
        return FinalObj

    def execute(self, context):
        oTargetObject = context.active_object
        oTFXProps = oTargetObject.TressFXProps

        #retreive stuff
        print("SETTINGS:")

        self.nNumVertsPerStrand = None
        self.oBaseMesh = None

        self.bDebugMode = oTFXProps.bDebugMode
        print('     bdebugMode: ' + str(self.bDebugMode))

        if oTFXProps.sBaseMesh and oTFXProps.sBaseMesh in bpy.data.objects:
            self.oBaseMesh = bpy.data.objects[oTFXProps.sBaseMesh]
            print('     Base Mesh: ' + self.oBaseMesh.name)
        else:
            self.report({'ERROR'}, "Base mesh not found!")
            return {'CANCELLED'}

        if oTFXProps.eNumVertsPerStrand is not None:
            self.nNumVertsPerStrand = int(oTFXProps.eNumVertsPerStrand)
            print('     nNumVertsPerStrand: ' + str(self.nNumVertsPerStrand))
        else:
            self.report({'ERROR'}, "Invalid num verts per strand!")
            return {'CANCELLED'}

        if oTFXProps.eExportType == 'PARTICLE_SYSTEM':
            
            self.eExportType = 'PARTICLE_SYSTEM'
            print('     eExportType: PARTICLE_SYSTEM')
            self.sParticleSystem = oTFXProps.sParticleSystem
            if oTFXProps.sParticleSystem is None or (oTFXProps.sParticleSystem is not None and len(oTFXProps.sParticleSystem) < 1):
                self.report({'ERROR'}, "Particle system was selected as export type, but no particle system was selected. Aborting.")
                return {'CANCELLED'}
            print('     sParticleSystem: ' + self.sParticleSystem)
        
        else:
            self.eExportType = 'CURVES'
            print('     eExportType: CURVES')

        self.eBoneExportMode = oTFXProps.eBoneExportMode
        print('     eBoneExportMode: ' + self.eBoneExportMode)
        self.ExportBones = oTFXProps.ExportBones
        
        if oTFXProps.eBoneExportMode != 'ALL_WITH_WEIGHT':
            if self.ExportBones is None or (self.ExportBones is not None and len(self.ExportBones) < 1):
                self.report({'ERROR'}, "Export mode was either BLACKLIST or WHITELIST, but no bones were found. Aborting.")
                return {'CANCELLED'}

        print('     Selected Bones: ')
        for b in self.ExportBones:
            print('         ' + b.sBoneName)
        print('     eBoneExportMode: ' +  self.eBoneExportMode)

        self.fMinCurvelength = oTFXProps.fMinimumCurveLength
        print('     fMinCurvlength: ' + str(self.fMinCurvelength))
        self.bBothEndsImmovable = oTFXProps.bBothEndsImmovable
        print('     bBothEndsImmovable: ' + str(self.bBothEndsImmovable))
        self.bInvertZAxis = oTFXProps.bInvertZAxis
        print('     bInvertZAxis: ' + str(self.bInvertZAxis))
        self.bInvertYAxisUV = oTFXProps.bInvertYAxisUV
        print('     bInvertYAxisUV: ' + str(self.bInvertYAxisUV))
        self.bRandomizeStrandsForLOD = oTFXProps.bRandomizeStrandsForLOD
        print('     bRandomizeStrandsForLOD: ' + str(self.bRandomizeStrandsForLOD))
        self.sOutputDir = oTFXProps.sOutputDir
        print('     sOutputDir: ' + str(self.sOutputDir))
        self.sOutputName = oTFXProps.sOutputName
        print('     sOutputName: ' + str(self.sOutputName))

        if len(self.sOutputDir) < 1:
            self.report({'ERROR'}, "Output directory not set. Aborting.")
            return {'CANCELLED'}

        if self.oBaseMesh.data.uv_layers.active is None:
            self.report({'ERROR'}, "No UV's found on base mesh. Aborting")
            return {'CANCELLED'}

        if self.oBaseMesh.parent.type != 'ARMATURE':
            self.report({'ERROR'}, "No armature found on base mesh. Aborting")
            return {'CANCELLED'}

        CurvesList = []

        if self.eExportType == 'PARTICLE_SYSTEM':
            #convert particle system to mesh using convert modifier
            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.scene.objects.active = self.oBaseMesh
            # CurvesList = ConvertParticleSystemHairsToCurves(self.oBaseMesh, self.sParticleSystem)
            
            bFound = False
            for mod in self.oBaseMesh.modifiers:
                if mod.type == 'PARTICLE_SYSTEM' and mod.particle_system.name == self.sParticleSystem:
                    print("Converting particle system '" + mod.particle_system.name + "' to mesh...")
                    bpy.ops.object.modifier_convert(modifier=mod.name)
                    bFound = True
                    break

            if bFound == False:
                self.report({'ERROR'}, "unable to find particle system: " + self.sParticleSystem + ". Aborting")
                return {'CANCELLED'}

            #new mesh should already be selected, convert it to curves
            bpy.ops.object.convert(target='CURVE')
            #separate them into invidual curves
            print('separating into individual curves...')
            CurvesList = SeparateCurves2(context)
        else:
            print("using selected curves as strands. Assuming they are already sperated into individual curve objects.")
            CurvesList = [p for p in bpy.context.scene.objects if p.select and p.type == 'CURVE']
        
        print(str(len(CurvesList)) + " curves found...")

        if len(CurvesList) < TRESSFX_SIM_THREAD_GROUP_SIZE:
            self.report({'ERROR'}, "Not enough curves found, at least " + str(TRESSFX_SIM_THREAD_GROUP_SIZE) + " curves are required!")
            return {'CANCELLED'}
        
        success = self.SaveTFXHairJsonFile(context, CurvesList)
        if success == 'ERROR':
            return {'CANCELLED'}

        if self.eExportType == 'PARTICLE_SYSTEM' and not self.bDebugMode:
            # delete the potentially thousands of curves we generated
            print('Deleting ' + str(len(CurvesList)) + ' temporary curves...')
            bpy.ops.object.select_all(action='DESELECT')
            for Curve in CurvesList:
                bpy.data.objects[Curve.name].select = True
            bpy.ops.object.delete()

        print('Done.')
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

classes = (
    FTressFXBoneProps,
    TressFXBoneListItems,
    FDirectorySelector,
    FTressFXExport,
    FTressFXCollisionExport,
    FTressFXPanel,
    FTressFXProps,
    TressFXBoneListItemsActions,
    TressFXBonesClearList,
    TressFXBonesRemoveDuplicates
)

def register():
    from bpy.utils import register_class
    for clss in classes:
        register_class(clss)

def unregister():
    from bpy.utils import unregister_class
    for clss in reversed(classes):
        unregister_class(clss)


if __name__ == "__main__":
    register()
    
    

