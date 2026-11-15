# 第三方来源与素材说明

## 已随仓库提供的支架几何

`assets/accessories/piper_camera_bracket_candidate.obj` 来源于 AgileX `piper_ros` 固定提交 `ac41fcbcdda598f01b51cf6175ed9a24d0dacadc` 的 `camera_v3.dae`。这是单独支架几何的提取与格式转换；完整处理记录在 `bracket_source_notes.json`。

原仓库采用 MIT License，Copyright (c) 2024 RosenYin。完整许可保留在 `assets/accessories/LICENSE.piper_ros.txt`，OBJ 头部同时保留来源与许可。预览图为该几何的检查视图，不代表实物尺寸验证。

## 按需获取的模型

M1 来源于 `zsibot/MATRiX_Python_SDK`，Piper H/夹爪来源于 `agilexrobotics/agx_arm_urdf`，版本和 URL 在 `config/sources.lock.json`。它们由用户本机下载到 `vendor/`，本开工提交不重新分发这些完整源资产。

以后提交转换或衍生网格时，需要一起保留相应上游来源与许可；不能把所有第三方模型自动归入本工程代码的许可。

## 用户照片

`materials/photos/` 的四张原始照片由仓库所有者提供，用于本项目安装参考。第三方支架的 MIT 许可不自动适用于这些照片。

本次没有替仓库所有者选择统一的项目开源许可证。公开可查看不等于将所有照片和第三方素材重新授权为任意使用。
