import netCDF4 as nc
import numpy as np
import matplotlib.pyplot as plt
import scipy
from scipy import ndimage
import csv
import sys
import os, re
from datetime import datetime
import matplotlib
import matplotlib.patches as patches

import ASTER_ncfiles
import water_detection_mask as wdm

import optimal_estimation as oe
import RTTOV_jacobian_files as kfiles





def masked_bt_nighttime(oe_sst, nc_file, landmask_file):	
	#BT10 = np.rot90(np.array(nc_file.variables['BT_band10']))
	#BT10_up = np.roll(BT10, -2, axis=0)
	#BT10_left= np.roll(BT10_up, -10, axis=1)
	sst_array = np.rot90(np.array(oe_sst))
	sst_array = np.roll(sst_array, -2, axis=0)
	sst_array= np.roll(sst_array, -10, axis=1)
	
	#pick your variables for the mask and for BT
	landmask = np.flipud(np.array(nc.Dataset(landmask_file).variables['Stat_landmask']))
	# Get the stat landmask
	a = np.ma.masked_equal(landmask, 0)
	aMask = np.ma.getmaskarray(a)
	# Apply the mask to the TIR data.
	#BT_masked = np.ma.array(BT10_left, mask=aMask, fill_value=np.nan)
	sst_masked = np.ma.array(sst_array, mask=aMask, fill_value=np.nan)
	#np.ma.set_fill_value(BT_masked, np.nan)
	return sst_masked #BT_masked

def stack_water_detection(filename, path, landmask_file):
	"""
	Input:
	filename - list of netcdf files with MNDWI mask
	path - absolute path to where the netcdf files are stored
	---
	loops through all files in the given list, finds the MNDWI masked layer
	for each layer gives value of 1 if land, 0 is water
	stacks the masks together as a 3D array
	---
	Output: 3D array of 0-1 masks
	"""
	
	k_prof = [kfiles.k_path + k_element for k_element in kfiles.k_files_torness]
	k_skin = [kfiles.k_skin_path + k_skin_element for k_skin_element in kfiles.k_skin_files_torness]
	
	#result_array = np.zeros((len(filename), 401, 401))
	result_array = np.empty((len(filename), 401, 401))
	dates_array = []
	for i, element in enumerate(filename):
	
		date_of_the_satellite_obs = re.findall(r"\d{8}", str(element)[45:60])
		ncfile_date = str(date_of_the_satellite_obs[0].strip().strip("'")) #int(date_of_the_satellite_obs[0])
		print ncfile_date
		rttov_date = datetime.strptime(ncfile_date, '%Y%m%d').strftime('%Y-%m-%d')
		print rttov_date
		
		#date_of_the_satellite_obs = element[21:29]
		element_path = os.path.join(path, element)
		
		for item1, item2 in zip(k_prof, k_skin):
			if rttov_date in item1 and rttov_date in item2:
				print 'YES IT WORKS!'
				oe_sst, tcwv = oe.oe_main('ASTER', element_path, item1, item2)
				
		nc_file = nc.Dataset(element_path)
		sst_masked = masked_bt_nighttime(oe_sst, nc_file, landmask_file)
	
	
		sst_masked[sst_masked > 350] = np.nan 
		sst_masked[sst_masked < 276] = np.nan
		#BT_masked[BT_masked.mask == True] = np.nan
		
		#my_cmap = matplotlib.cm.rainbow 
		#my_cmap.set_bad(color='white', alpha=0.75)

		#plt.imshow(BT_masked) #, cmap= my_cmap)
		#plt.title('Shifted BT nighttime with statistical landmask')
		#plt.show()
		
		result_array[i,:,:] = sst_masked
		print "results array" , result_array[i,:,:]
		"""
		date = re.findall(r"\d{8}", str(element)[50:61]) #[46:54]) 
		#print date
		#print str(element)[50:61] #[46:54] 
		value = str(date[0].strip().strip("'"))
		#print value
		dates_array.append(value)
		"""

		
	#print np.shape(result_array)
	return result_array #, dates_array

def subimage(image_as_array, step):
	"""
	Get a sub-image from original image.
	Sub-image and original image share the centre.
	The outer bounds of sub-image are specified by the step_count_from_centre argument.
	step - step size from the centre expressed as number of pixels
	"""
	subimage_2d_array = image_as_array[200-int(step):200+int(step)]
	return subimage_2d_array

def centered_average(nums):
	#print np.nansum(nums)
	#print np.nanmax(nums)
	#print np.nanmin(nums)
	#print len(nums) - 2
	return (np.nansum(nums) - np.nanmax(nums) - np.nanmin(nums)) / (np.count_nonzero(~np.isnan(nums)) - 2)	

def morphological_dilation(masked_image, n): #n=3
	"""
	Extending the landmask.
	Should extend the landmask over the image for 3 pixels (0.0015 degrees)
	----------
	from stackoverflow:
	def dilation(a, n):
	m = np.isnan(a)
	s = np.full(n, True, bool)
	return ndimage.binary_dilation(m, structure=s, origin=-(n//2))
	-----------
	For sparse initial masks and small n this one is also pretty fast:
	def index_expansion(a, n):
	mask = np.isnan(a)
	idx = np.flatnonzero(mask)
	expanded_idx = idx[:,None] + np.arange(1, n)
	np.put(mask, expanded_idx, True, 'clip')
	return mask
	"""
	mask = np.isnan(masked_image)
	s = ndimage.morphology.generate_binary_structure(2, 1)
	extended_mask = ndimage.binary_dilation(mask, structure=s, iterations=3).astype(mask.dtype)
	return extended_mask

def choose_plume(image_thresholded):
	
	#now find the objects
	where_are_NaNs = np.isnan(image_thresholded)
	image_thresholded[where_are_NaNs] = 0
	
	labeled_image, numobjects = ndimage.label(image_thresholded)
	
	#plt.imshow(labeled_image)
	#plt.title('Labeled image')
	#plt.show()
	
	object_areas = np.bincount(labeled_image.ravel())[:]
	#to exclude the first object which is background , index from 1
	#object_idx = [i for i in range(1, numobjects+1) if 1000 > object_areas[i] > 5]
	object_idx = [i for i in range(1, numobjects+1) if 1500 > object_areas[i] > 5]
	print('object area' , object_areas)
	print('object idx' , object_idx)
	# Remove small white regions
	#labeled_image = ndimage.binary_opening(labeled_image)
	# Remove small black hole
	#labeled_image = ndimage.binary_closing(labeled_image)
	chosen_object = [0,50]
	for object in object_idx: #range(0,numobjects):
		#object = object + 1
		#print('object' , object)
		iy, ix = np.where(labeled_image == object)
		centridx_y = 200 #175
		centridx_x = 200 #230
		min_dist = np.min(np.sqrt((np.abs(centridx_y - iy))**2 + (np.abs(centridx_x - ix))**2))
		if min_dist < chosen_object[1]:
			chosen_object = [object, min_dist]
		#print(object , min_dist)
	print('Chosen object' , chosen_object)
	#chosen_plume = np.where((labeled_image == chosen_object[0]), chosen_object[0], 0)
	if chosen_object[1] == 50:
		chosen_plume = np.zeros_like(labeled_image)
	else:
		chosen_plume = np.where((labeled_image == chosen_object[0]), 1, 0)
	area = sum(sum(i == True for i in chosen_plume))
	print "Detected plume area (number of pixels):" , area
	return chosen_plume

def morphological_dilation(masked_image, n): #n=3
	"""
	Extending the landmask.
	Should extend the landmask over the image for 3 pixels (0.0015 degrees)
	----------
	from stackoverflow:
	def dilation(a, n):
	m = np.isnan(a)
	s = np.full(n, True, bool)
	return ndimage.binary_dilation(m, structure=s, origin=-(n//2))
	-----------
	For sparse initial masks and small n this one is also pretty fast:
	def index_expansion(a, n):
	mask = np.isnan(a)
	idx = np.flatnonzero(mask)
	expanded_idx = idx[:,None] + np.arange(1, n)
	np.put(mask, expanded_idx, True, 'clip')
	return mask
	"""
	mask = np.isnan(masked_image)
	s = ndimage.morphology.generate_binary_structure(2, 1)
	extended_mask = ndimage.binary_dilation(mask, structure=s, iterations=3).astype(mask.dtype)
	return extended_mask


######################################################
def ASTER_plume_main():

	filename1 = ASTER_ncfiles.heysham_tir
	path1 = ASTER_ncfiles.heysham_path
	mask = '/home/users/mp877190/CODE/plume_detection_clustering/Heysham_landmask.nc'
	masked_stack1 = stack_water_detection(filename1, path1, mask)

	filename2 = ASTER_ncfiles.heysham_1999_tir
	path2 = ASTER_ncfiles.heysham_1999_path
	masked_stack2 = stack_water_detection(filename2, path2, mask)

	masked_stack = np.concatenate((masked_stack1, masked_stack2),axis=0)
	

	plume_array = np.zeros_like(masked_stack)
	for i, layer in enumerate(masked_stack):
	
		#expand land mask by morphological dilation
		#extended_landmask = morphological_dilation(mask, 20)
		#layer[extended_landmask] = np.nan
		
		BT_Celsius = layer - 273.15

		#plt.imshow(BT_Celsius, cmap='RdBu_r')
		#plt.title('BT nighttime with statistical landmask \n image %d' %i)
		#plt.colorbar()
		#plt.show()
		
		# get a central part of the image
		sub_layer = subimage(BT_Celsius, 25)
		ambient = centered_average(BT_Celsius[150:250, 0:100]) #[0:100, 250:350])
		accepted_thresh = np.float(ambient) + 1.5 #np.float(max_val) -  np.float(ambient)
		#accepted_thresh = np.float(centered_average(BT_Celsius)) + (3.0 * np.nanstd(BT_Celsius))
		
		#print('accepted threshold' , accepted_thresh)
		threshold   = accepted_thresh
		image_thresh = np.copy(BT_Celsius)
		image_thresh[image_thresh<threshold] = np.nan
		plume = choose_plume(image_thresh)
		
		#plt.imshow(plume)
		#plt.title('Detected plume %d' %i)
		#plt.show()
		
		plume_array[i,:,:] = plume
		end_result = np.nansum(plume_array, axis=0)
		end_result = (end_result / np.amax(end_result)) * 100
	return plume_array
"""
## PLOT THE PROBABILITY DENSITY MAP 
my_cmap = matplotlib.cm.hot_r 
my_cmap.set_under(color='paleturquoise') #, alpha=0.5)
plt.imshow(end_result, cmap= my_cmap, vmin=1)
plt.colorbar()
plt.title('HEYSHAM \n Probability of plume extent from nighttime ASTER imagery')
plt.tight_layout()
plt.show()
"""
