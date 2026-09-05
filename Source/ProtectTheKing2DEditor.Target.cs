// Protect the King — 2D. Editor target.

using UnrealBuildTool;
using System.Collections.Generic;

public class ProtectTheKing2DEditorTarget : TargetRules
{
	public ProtectTheKing2DEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.V7;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_8;
		ExtraModuleNames.Add("ProtectTheKing2D");
	}
}
