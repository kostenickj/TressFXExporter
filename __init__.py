bl_info = {
    "name": "TressFX Exporter",
    "author": "Kostenick, Jacob",
    "version": (0, 0, 1),
    "blender": (2, 79, 0),
    "description": "YEET",
    "warning": "",
    "wiki_url": "",
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
from bpy_extras.io_utils import ExportHelper

thisdir = os.path.dirname(__file__)
if not thisdir in sys.path:
    sys.path.append(thisdir )

import CurveSimplifier as simp


class TressFXTFXFileHeader(ctypes.Structure):
	_fields_ = [('version', ctypes.c_float),
                ('numHairStrands', ctypes.c_uint),
                ('numVerticesPerStrand', ctypes.c_uint),
                ('offsetVertexPosition', ctypes.c_uint),
                ('offsetStrandUV', ctypes.c_uint),
                ('offsetVertexUV', ctypes.c_uint),
                ('offsetStrandThickness', ctypes.c_uint),
                ('offsetVertexColor', ctypes.c_uint),
                ('reserved', ctypes.c_uint * 32)]

class TressFX_Float4(ctypes.Structure):
	_fields_ = [('x', ctypes.c_float),
                ('y', ctypes.c_float),
                ('z', ctypes.c_float),
                ('w', ctypes.c_float)]

class TressFX_Float2(ctypes.Structure):
	_fields_ = [('x', ctypes.c_float),
                ('y', ctypes.c_float)]


#__________________________________________________________________________
# p0, p1, p2 are three vertices of a triangle and p is inside the triangle
def ComputeBarycentricCoordinates(p0, p1, p2, p):
	v0 = p1 - p0
	v1 = p2 - p0
	v2 = p - p0

	v00 = v0 * v0
	v01 = v0 * v1
	v11 = v1 * v1
	v20 = v2 * v0
	v21 = v2 * v1
	d = v00 * v11 - v01 * v01
	v = (v11 * v20 - v01 * v21) / d # TODO: Do I need to care about divide-by-zero case?
	w = (v00 * v21 - v01 * v20) / d
	u = 1.0 - v - w

	# make sure u, v, w are non-negative. It could happen sometimes.
	u = max(u, 0)
	v = max(v, 0)
	w = max(w, 0)

	# normalize barycentric coordinates so that their sum is equal to 1
	sum = u + v + w
	u /= sum
	v /= sum
	w /= sum

	return [u, v, w]


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

def SeparateCurves(context):
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
        
        FTressFXProps.sOutputName = bpy.props.StringProperty(
            name="Export File Name", 
            description="The export filename without extension",
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
    Base Mesh must be all triangles!
    Assumes that the selected UV map on the base mesh is the one to use when generating UV's for the hairs.
    '''    

    #NOTE bl_idname has to be all lowercase :(
    bl_idname = "tressfx.export"
    bl_label = "TressFX: Export"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def SaveTFXBinaryFile(self, context, lHairs):
        nNumCurves = len(lHairs)
        RootPositions = []

        tfxHeader = TressFXTFXFileHeader()
        tfxHeader.version = 4.0
        tfxHeader.numHairStrands = nNumCurves
        tfxHeader.numVerticesPerStrand = self.nNumVertsPerStrand
        tfxHeader.offsetVertexPosition = ctypes.sizeof(TressFXTFXFileHeader)
        tfxHeader.offsetStrandUV = 0
        tfxHeader.offsetVertexUV = 0
        tfxHeader.offsetStrandThickness = 0
        tfxHeader.offsetVertexColor = 0

        tfxHeader.offsetStrandUV = tfxHeader.offsetVertexPosition + nNumCurves * self.nNumVertsPerStrand * ctypes.sizeof(TressFX_Float4)
        
        OutFilePath = self.sOutputDir + (self.sOutputName if len(self.sOutputName) > 0 else self.oBaseMesh.name)  + ".tfx"
        print(OutFilePath)
        TfxFile = open(OutFilePath, "wb")
        TfxFile.write(tfxHeader)

        for nHairIdx, CurveObj in enumerate(lHairs):

            #we need to subdivide the curve if it has less points than self.nNumVertsPerStrand
            CorrectCurve = RecursiveSubdivideCurveIfNeeded(context, CurveObj, self.nNumVertsPerStrand)
            CurvePoints = [(vert.x, vert.y, vert.z) for vert in [p.co for p in CorrectCurve.data.splines[0].points]]
            
            #now resample to exactly nNumVertsPerStrand if needed
            if len(CurvePoints) != self.nNumVertsPerStrand:
                Simplifier = simp.Simplifier(CurvePoints)
                # uses Visvalingam-Whyatt method
                SimplifiedCurve = Simplifier.simplify( number=self.nNumVertsPerStrand )
                CurvePoints = SimplifiedCurve

            # now we ready to write the points
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
                
                TfxFile.write(p)
            # enumerate(CurvePoints):
            RootPositions.append(CurvePoints[0])
        # enumerate(lHairs):
        
        # get strand texture coords
        for nPtIdx, Point in enumerate(RootPositions):
            
            pVector = mathutils.Vector((Point[0],Point[1],Point[2]))

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
            #print('Location:' + str(Location))
            #print('UV: ' + str(UVAtPoint.xy))
            UVCoord = TressFX_Float2()
            UVCoord.x = UVAtPoint.x
            UVCoord.y = UVAtPoint.y
            if self.bInvertYAxisUV:
                UVCoord.y = 1.0 - UVCoord.y; # DirectX has it inverted
            
            TfxFile.write(UVCoord)
        #enumerate(RootPositions)

        TfxFile.close()
        return RootPositions

    def SaveTFXBoneBinaryFile(self, context, RootPositions): 

        vertexTriangleList = []
        triangleIdForStrandsList = []
        baryCoordList = []
        pointOnMeshList = []

        for nPtIdx, Point in enumerate(RootPositions):

            pVector = mathutils.Vector((Point[0],Point[1],Point[2]))
	        # Find the closest point info
            bResult, Location, Normal, FaceIndex = self.oBaseMesh.closest_point_on_mesh(pVector)
            TriangleIndices = self.oBaseMesh.data.polygons[FaceIndex].vertices

            pointOnMesh = mathutils.Vector((Location[0],Location[1],Location[2]))
            
            pointOnMeshList.append(pointOnMesh)
            vertexTriangleList.append((TriangleIndices[0], TriangleIndices[1], TriangleIndices[2]))
            triangleIdForStrandsList.append(FaceIndex)
            
            # the 3 points that make up the triangle
            p0, p1, p2 = [self.oBaseMesh.data.vertices[TriangleIndices[i]].co for i in range(3)]
    
            uvw_a = ComputeBarycentricCoordinates(p0, p1, p2, pointOnMesh)
            uvw = mathutils.Vector((0,0,0))

            uvw.x = uvw_a[0]
            uvw.y = uvw_a[1]
            uvw.z = uvw_a[2]

            uvw.x = max(uvw.x, 0)
            uvw.y = max(uvw.y, 0)
            uvw.z = max(uvw.z, 0)

            Sum = uvw.x + uvw.y + uvw.z
            uvw.x /= Sum
            uvw.y /= Sum
            uvw.z /= Sum

            baryCoordList.append(uvw)
        print('ok')


    def execute(self, context):
        oTargetObject = context.active_object
        oTFXProps = oTargetObject.TressFXProps

        #retreive stuff
        print("SETTINGS:")

        self.nNumVertsPerStrand = None
        self.oBaseMesh = None

        if oTFXProps.sBaseMesh and oTFXProps.sBaseMesh in bpy.data.objects:
            self.oBaseMesh = bpy.data.objects[oTFXProps.sBaseMesh]
            print('     Base Mesh: ' + self.oBaseMesh.name)
        else:
            self.report({'WARNING'}, "Base mesh not found!")
            return {'CANCELLED'}

        if oTFXProps.eNumVertsPerStrand is not None:
            self.nNumVertsPerStrand = int(oTFXProps.eNumVertsPerStrand)
            print('     nNumVertsPerStrand: ' + str(self.nNumVertsPerStrand))
        else:
            self.report({'WARNING'}, "Invalid num verts per strand!")
            return {'CANCELLED'}

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
        self.bExportTFX = oTFXProps.bExportTFX
        print('     bExportTFX: ' + str(self.bExportTFX))
        self.bExportTFXBone = oTFXProps.bExportTFXBone
        print('     bExportTFXBone: ' + str(self.bExportTFXBone))
        self.sOutputDir = oTFXProps.sOutputDir
        print('     sOutputDir: ' + str(self.sOutputDir))
        self.sOutputName = oTFXProps.sOutputName
        print('     sOutputName: ' + str(self.sOutputName))

        if len(self.sOutputDir) < 1:
            self.report({'WARNING'}, "Output directory not set. Aborting.")
            return {'CANCELLED'}

        if self.bExportTFX == False and self.bExportTFXBone == False:
            self.report({'WARNING'}, "Nothing selected to export. Aborting.")
            return {'CANCELLED'}

        if self.oBaseMesh.data.uv_layers.active is None:
            self.report({'WARNING'}, "No UV's found on base mesh. Aborting")
            return {'CANCELLED'}

        #TODO option to use existing curves or particle system, gonna start with particle system only
        ExportMethod = 'PARTICLE SYSTEM'

        if ExportMethod == 'PARTICLE SYSTEM':
            #convert particle system to mesh using convert modifier
            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.scene.objects.active = self.oBaseMesh

            for mod in self.oBaseMesh.modifiers:
                if mod.type == 'PARTICLE_SYSTEM':
                    print("Converting particle system '" + mod.name + "' to mesh...")
                    bpy.ops.object.modifier_convert(modifier=mod.name)
                    #TODO have user select the particle system instead of just picking the
                    # first one i come across
                    break
                    
            #new mesh should already be selected
            bpy.ops.object.convert(target='CURVE')
            SeparateCurves(context)
        else:
            print("using selected curves as strands")

        CurvesList = [p for p in bpy.context.scene.objects if p.select and p.type == 'CURVE']
        print(str(len(CurvesList)) + " curves found...")
        
        RootPositions = []
        
        if self.bExportTFX:
            RootPositions = self.SaveTFXBinaryFile(context, CurvesList)

        if self.bExportTFXBone:
            self.SaveTFXBoneBinaryFile(context, RootPositions)

        if ExportMethod == 'PARTICLE SYSTEM':
            # delete the potentially thousands of curves we generated
            print('Deleting ' + str(len(CurvesList)) + ' temporary curves...')
            bpy.ops.object.select_all(action='DESELECT')
            for Curve in CurvesList:
                bpy.data.objects[Curve.name].select = True
            bpy.ops.object.delete()

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
    
    

