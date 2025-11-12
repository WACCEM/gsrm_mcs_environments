from matplotlib.colors import LinearSegmentedColormap



#### define colormaps
whiteTOblueTOgreen = LinearSegmentedColormap.from_list('mycmap',
                                                ['white','#ece2f0','#d0d1e6','#a6bddb','#67a9cf',
                                                '#3690c0','#02818a','#016c59','#014636'])

brownTOwhiteTOgreen = LinearSegmentedColormap.from_list('mycmap', 
                                          ['#543005','#8c510a',
                                          '#bf812d','#dfc27d','white','white',
                                           '#80cdc1','#35978f','#01665e','#003c30'])
blueTOwhiteTOred =  LinearSegmentedColormap.from_list('mycmap', 
                                          ['#053061','#2166ac','#4393c3','#92c5de','#d1e5f0',
                                           'white','white','#fddbc7','#f4a582','#d6604d','#b2182b',
                                              '#67001f'])
whiteTOblueTOgreenToPurple = LinearSegmentedColormap.from_list('mycmap',
                                                ['white','#ece2f0','#d0d1e6','#a6bddb','#67a9cf',
                                                '#3690c0','#02818a','#016c59','#542788',
                                                 '#c51b7d'])

spectral_cyclic = LinearSegmentedColormap.from_list('mycmap',
                                                ['#9e0142', '#5e4fa2','#3288bd', '#66c2a5','#abdda4',
                                            '#e6f598','#ffffbf','#fee08b','#fdae61','#f46d43','#d53e4f','#9e0142',])
