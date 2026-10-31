// @(#)OpticalFlowCheck.swift 3.1 2026/10/31 11:30:00
import Foundation
import Vision
import CoreVideo
let w=160, h=128
var seed: UInt64=12345
var texture=[UInt8](repeating:0,count:w*h)
for i in 0..<texture.count { seed = seed &* 6364136223846793005 &+ 1; texture[i] = UInt8((seed >> 32) & 255) }
func frame(_ dx: Int,_ dy: Int) -> CVPixelBuffer {
 var b: CVPixelBuffer?; CVPixelBufferCreate(nil,w,h,kCVPixelFormatType_32BGRA,[kCVPixelBufferIOSurfacePropertiesKey: [:]] as CFDictionary,&b)
 let p=b!; CVPixelBufferLockBaseAddress(p,[])
 let data=CVPixelBufferGetBaseAddress(p)!.assumingMemoryBound(to: UInt8.self), stride=CVPixelBufferGetBytesPerRow(p)
 for y in 0..<h { for x in 0..<w { let sx=x-dx, sy=y-dy; let v: UInt8 = sx>=0 && sx<w && sy>=0 && sy<h ? texture[(sy/4*4)*w+(sx/4*4)] : 0
 for c in 0..<3 { data[y*stride+4*x+c]=v }; data[y*stride+4*x+3]=255 } }
 CVPixelBufferUnlockBaseAddress(p,[]); return p
}
let old=frame(0,0), new=frame(8,4)
let request=VNGenerateOpticalFlowRequest(targetedCVPixelBuffer: new,options: [:]); request.revision=1; request.computationAccuracy = .low
try VNImageRequestHandler(cvPixelBuffer:old,orientation:.up,options:[:]).perform([request])
let flow=request.results!.first!.pixelBuffer
CVPixelBufferLockBaseAddress(flow,.readOnly)
var xs=[Float](), ys=[Float]()
for y in 32..<96 { let row=CVPixelBufferGetBaseAddress(flow)!.advanced(by:y*CVPixelBufferGetBytesPerRow(flow)).assumingMemoryBound(to:Float.self)
 for x in 32..<128 { xs.append(row[2*x]); ys.append(row[2*x+1]) } }
xs.sort(); ys.sort(); assert(abs(xs[xs.count/2]-8) < 0.3 && abs(ys[ys.count/2]-4) < 0.3); print("Vision flow direction verified: +8/+4 pixels"); CVPixelBufferUnlockBaseAddress(flow,.readOnly)
