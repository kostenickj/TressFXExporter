# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# Copyright (C) 2017 JOSECONSCO
# Created by JOSECONSCO

import bpy
import math
import numpy as np
from bpy.props import EnumProperty, FloatProperty, BoolProperty, IntProperty, StringProperty
from resample2d import interpol_Catmull_Rom, get_strand_proportions
   
def SimplifyCurve(context, curveObj, numPointsToKeep):

    pointsList = []
    pointsRadius = []
    pointsTilt = []
    selectedSplines = [curveObj.data.splines[0]]

    for polyline in selectedSplines:  # for strand point
        if polyline.type == 'NURBS' or polyline.type == 'POLY':
            points = polyline.points
        else:
            points = polyline.bezier_points
        if len(points) > 1:  # skip single points
            pointsList.append([point.co.to_3d() for point in points])
            pointsRadius.append([point.radius for point in points])
            pointsTilt.append([point.tilt for point in points])
    
    interpolRad = []
    interpolTilt = []
    uniformPointSpacing = True
    equalPointCount = True
    splinePointsList = interpol_Catmull_Rom(pointsList, numPointsToKeep, uniform_spacing = uniformPointSpacing, same_point_count= equalPointCount)
    

    t_ins_y = [i / (numPointsToKeep - 1) for i in range(numPointsToKeep)]
    for radii, tilts in zip(pointsRadius, pointsTilt):  # per strand
        t_rad = [i / (len(radii) - 1) for i in range(len(radii))]
        interpolRad.append(np.interp(t_ins_y, t_rad, radii))  # first arg len() = out len
        interpolTilt.append(np.interp(t_ins_y, t_rad, tilts))  # first arg len() = out len


    curveData = curveObj.data
    curveData.splines.clear()

    newSplines = []
    for k, splinePoints in enumerate(splinePointsList):  # for each strand/ring
        curveLenght = len(splinePoints)
        polyline = curveData.splines.new('POLY')
        newSplines.append(polyline)
        polyline.points.add(curveLenght - 1)

        
        np_splinePointsOnes = np.ones((len(splinePoints), 4))  # 4 coord x,y,z ,1
        np_splinePointsOnes[:, :3] = splinePoints
        polyline.points.foreach_set('co', np_splinePointsOnes.ravel())
        polyline.points.foreach_set('radius', interpolRad[k])
        polyline.points.foreach_set('tilt', interpolTilt[k])

    curveData.resolution_u = 12
    return curveObj
