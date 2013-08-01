/**
 * TheVirtualBrain-Framework Package. This package holds all Data Management, and 
 * Web-UI helpful to run brain-simulations. To use it, you also need do download
 * TheVirtualBrain-Scientific Package (for simulators). See content of the
 * documentation-folder for more details. See also http://www.thevirtualbrain.org
 *
 * (c) 2012-2013, Baycrest Centre for Geriatric Care ("Baycrest")
 *
 * This program is free software; you can redistribute it and/or modify it under 
 * the terms of the GNU General Public License version 2 as published by the Free
 * Software Foundation. This program is distributed in the hope that it will be
 * useful, but WITHOUT ANY WARRANTY; without even the implied warranty of 
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
 * License for more details. You should have received a copy of the GNU General 
 * Public License along with this program; if not, you can download it here
 * http://www.gnu.org/licenses/old-licenses/gpl-2.0
 *
 **/

var plot = null;

function drawHistogram(canvasId, data, labels, colors) {
    colors = computeColors(colors);
    var histogramLabels = [];
    var histogramData = [];
    for (var i = 0; i < data.length; i++) {
        histogramData.push({data: [[i, parseFloat(data[i])]], color: colors[i]});
        histogramLabels.push([i, labels[i]]);
    }

    var options = {
        series: {stack: 0,
                 lines: {show: false, steps: false },
                 bars: {show: true, barWidth: 0.9, align: 'center'}},
        xaxis: {ticks: histogramLabels,
                labelWidth: 100,
                shouldRotateLabels: true}
    };

    plot = $.plot($("#" + canvasId), histogramData, options);
}

function computeColors(colorsArray) {
    // Compute actual colors from input array of numbers.
    var minColor = parseFloat($('#colorMinId').val());
    var maxColor = parseFloat($('#colorMaxId').val());
    var result = [];
    for (i = 0; i < colorsArray.length; i++) {
        var color = getGradientColorString(colorsArray[i], minColor, maxColor);
        result.push(color);
    }
    return result
}

function changeColors() {
    var originalColors = $('#originalColors').val().replace('[','').replace(']','').split(',');
    var newColors = computeColors(originalColors);
    var data = plot.getData();
    for (var i = 0; i < data.length; i++) {
        data[i].color = newColors[i];
    }
    plot.draw();
}