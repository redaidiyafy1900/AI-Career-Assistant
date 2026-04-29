将你的固定数字人模型文件放在此目录。

文件名建议：
- avatar.glb        // 首选加载
- fallback.glb      // 备选模型（可选）

要求：
- glTF 2.0 二进制（.glb），若包含面部表情，推荐带 ARKit morph targets（如 jawOpen/mouthSmile/browInnerUp）。
- 纹理应内嵌（嵌入式）以避免外链跨域问题。

放置后刷新 /interview_avatar.html 即可本地加载。