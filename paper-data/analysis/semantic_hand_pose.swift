// Optional independent *detector agreement* diagnostic, not ground-truth labeling.
// Native Apple Vision, fixed request revision; no image upload or model download.
import Foundation
import Vision
import ImageIO
import CryptoKit
import Darwin

struct Frame: Decodable {
    let id: String
    let image: String
    let sha256: String
}
struct Manifest: Decodable { let frames: [Frame] }
enum AuditError: Error, CustomStringConvertible {
    case message(String)
    var description: String { switch self { case .message(let s): return s } }
}
func digest(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}
func emit(_ record: [String: Any], to handle: FileHandle) throws {
    var line = try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys])
    line.append(0x0a)
    try handle.write(contentsOf: line)
}
func errorRecord(_ error: Error) -> [String: Any] {
    let ns = error as NSError
    return ["domain": ns.domain, "code": ns.code, "message": String(describing: error)]
}

func main() throws {
    let args = Array(CommandLine.arguments.dropFirst())
    guard args.count == 2 else {
        throw AuditError.message("Usage: semantic_hand_pose BLIND_MANIFEST.json|- NEW_OUTPUT.jsonl. Input frames: [{id,image:absolute_path,sha256}]. Output must not already exist.")
    }
    let data = try args[0] == "-" ? FileHandle.standardInput.readToEnd() ?? Data()
        : Data(contentsOf: URL(fileURLWithPath: args[0]))
    let root = try JSONSerialization.jsonObject(with: data)
    guard let obj = root as? [String: Any], Set(obj.keys) == ["frames"],
          let rows = obj["frames"] as? [[String: Any]], !rows.isEmpty,
          rows.allSatisfy({ Set($0.keys) == ["id", "image", "sha256"] }) else {
        throw AuditError.message("Expected BLIND manifest with only frames [{id,image,sha256}]; run names, policy labels, VLM outputs and prior labels are not accepted.")
    }
    let manifest = try JSONDecoder().decode(Manifest.self, from: data)
    guard Set(manifest.frames.map(\.id)).count == manifest.frames.count,
          manifest.frames.allSatisfy({ !$0.id.isEmpty && $0.image.hasPrefix("/") &&
              $0.sha256.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil }) else {
        throw AuditError.message("IDs must be unique/nonempty, image paths absolute, and SHA-256 values lowercase 64-digit hexadecimal.")
    }
    let fd = open(args[1], O_WRONLY | O_CREAT | O_EXCL, S_IRUSR | S_IWUSR)
    guard fd >= 0 else { throw AuditError.message("Cannot create NEW output (existing files are never overwritten): \(String(cString: strerror(errno)))") }
    let output = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
    defer { try? output.close() }
    let manifestHash = digest(data)
    let os = ProcessInfo.processInfo.operatingSystemVersionString
    let meta: [String: Any] = [
        "record_type": "metadata", "schema_version": 1,
        "label_source": "automated_detector", "detector": "Apple Vision VNDetectHumanHandPoseRequest",
        "request_revision": 1, "maximum_hand_count": 6, "image_orientation": "up",
        "os_version": os, "manifest_sha256": manifestHash, "frame_count": manifest.frames.count,
        "started_at_utc": ISO8601DateFormatter().string(from: Date()),
        "interpretation": "Detector observations only. no_detection does NOT mean no_hand. Confidences are not calibrated probabilities. Not ground truth or independent accuracy validation.",
        "model_weights_sha256": NSNull(),
        "weight_provenance_limit": "OS-managed Vision model weights are not separately fingerprinted. Pin OS build and request revision."
    ]
    try emit(meta, to: output)
    var frameErrors = 0
    var detectionFrames = 0
    let started = ProcessInfo.processInfo.systemUptime
    for frame in manifest.frames {
        try autoreleasepool {
            let tick = ProcessInfo.processInfo.systemUptime
            var record: [String: Any] = [
                "record_type": "frame", "id": frame.id, "image": frame.image,
                "expected_sha256": frame.sha256, "label_source": "automated_detector",
                "request_revision": 1, "maximum_hand_count": 6,
                "status": "error", "num_detections": NSNull(), "hands": [], "errors": []
            ]
            do {
                let bytes = try Data(contentsOf: URL(fileURLWithPath: frame.image))
                let actualHash = digest(bytes)
                record["actual_sha256"] = actualHash
                guard actualHash == frame.sha256 else { throw AuditError.message("Image SHA-256 mismatch; inference not performed") }
                let request = VNDetectHumanHandPoseRequest()
                request.revision = 1
                request.maximumHandCount = 6
                // Decode the exact verified bytes, not a path that may change after hashing.
                let handler = VNImageRequestHandler(data: bytes, orientation: .up, options: [:])
                try handler.perform([request])
                let observations = request.results ?? []
                var hands: [[String: Any]] = []
                var jointErrors: [[String: Any]] = []
                for (index, hand) in observations.enumerated() {
                    var result: [String: Any] = ["index": index, "observation_confidence": hand.confidence]
                    do {
                        let points = try hand.recognizedPoints(.all)
                        result["joints"] = points.map { key, value in
                            ["name": key.rawValue.rawValue, "x_normalized": value.location.x,
                             "y_normalized": value.location.y, "confidence": value.confidence] as [String: Any]
                        }.sorted { ($0["name"] as! String) < ($1["name"] as! String) }
                    } catch {
                        result["joints"] = []
                        result["error"] = errorRecord(error)
                        jointErrors.append(errorRecord(error))
                    }
                    hands.append(result)
                }
                record["hands"] = hands
                record["num_detections"] = observations.count
                record["status"] = observations.isEmpty ? "no_detection" : "detection"
                record["errors"] = jointErrors
                if !jointErrors.isEmpty { frameErrors += 1; record["status"] = "partial_error" }
                if !observations.isEmpty { detectionFrames += 1 }
            } catch {
                record["errors"] = [errorRecord(error)]
                frameErrors += 1
            }
            record["elapsed_s"] = ProcessInfo.processInfo.systemUptime - tick
            try emit(record, to: output)
        }
    }
    try emit([
        "record_type": "summary", "processed_frames": manifest.frames.count,
        "frames_with_detection": detectionFrames, "frames_with_error": frameErrors,
        "elapsed_s": ProcessInfo.processInfo.systemUptime - started,
        "finished_at_utc": ISO8601DateFormatter().string(from: Date()),
        "interpretation": "Counts describe detector output, not hand prevalence or detection accuracy."
    ], to: output)
    try output.synchronize()
    if frameErrors > 0 { exit(2) }
}
do { try main() }
catch { FileHandle.standardError.write(Data("semantic_hand_pose: \(error)\n".utf8)); exit(1) }
