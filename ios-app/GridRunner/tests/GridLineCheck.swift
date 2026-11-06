// @(#)GridLineCheck.swift 3.1.tiles.2 2026/11/05 17:30:00
import Foundation
import simd

@main struct GridLineCheck {
    static func main() {
        let w=480,h=640
        let k=simd_double3x3(columns:(SIMD3(600,0,0),SIMD3(0,600,0),SIMD3(240,320,1)))
        let gravity=SIMD3<Double>(0,0,-1)
        var config=GridConfiguration()
        config.leftMM = 26
        func image(offset:Double?=nil,angle:Double=0,cross:Bool=false,second:Bool=false,blank:Bool=false) -> [UInt8] {
            var pixels=[UInt8](repeating:210,count:w*h)
            if blank { return pixels }
            for y in 0..<h {
                let forward=Double(y-320)*85/600-200
                let left=(offset ?? config.leftMM)+tan(angle)*forward
                let x=Int((240+(left-config.leftMM)*600/85).rounded())
                for xx in max(0,x-4)...min(w-1,x+4) { pixels[y*w+xx]=25 }
                if second { for xx in 330...338 { pixels[y*w+xx]=25 } }
                if cross && (abs(y-224)<=8 || abs(y-416)<=8) {
                    for xx in 0..<w { pixels[y*w+xx]=25 }
                }
            }
            return pixels
        }
        func detect(_ pixels:[UInt8]) -> GridDetection {
            pixels.withUnsafeBufferPointer { GridLine.detect(luma:$0.baseAddress!,width:w,height:h,stride:w,k:k,gravity:gravity,config:config) }
        }
        let centered=detect(image())
        precondition(centered.valid && abs(centered.offset-config.leftMM)<0.15 && abs(centered.correction)<0.002)
        precondition(abs(centered.first.x-0.5)<0.003) // The camera itself is above the stripe.
        precondition(abs(centered.targetFirst.x-centered.first.x)<0.003)
        for direction:Int8 in [-1,1] {
            config.direction=direction
            for offset in [-8.0,8.0] {
                let d=detect(image(offset:config.leftMM+offset))
                precondition(d.valid && abs(d.offset-config.leftMM-offset)<0.3 && d.correction*offset>0)
            }
            let angled=detect(image(angle:0.025))
            precondition(angled.valid && abs(angled.angle-0.025)<0.006 && abs(angled.offset-config.leftMM)<1.2)
            precondition(angled.correction*Double(direction)>0)
        }
        precondition(detect(image(cross:true)).valid)
        precondition(!detect(image(blank:true)).valid)
        precondition(!detect(image(second:true)).valid)
        config.direction = -1
        var p=GridPacket();p.session=11;p.calibration=22;p.sequence=7;p.flags=3;p.reason=0
        p.frameUS=2900000;p.sendUS=3010000;p.config=config;p.direction=config.direction;p.detection=detect(image())
        p.crossing.valid=true;p.crossing.count=3;p.crossing.lastCrossing=2.9
        p.crossing.y=0.5012;p.crossing.confidence=0.97;p.crossing.lastInterval=3.06
        print(p.encoded().map { String(format:"%02x",$0) }.joined())
        print("offset, angle, both travel polarities, camera-centered mount compensation, transverse stripes, loss and ambiguity verified")
    }
}
