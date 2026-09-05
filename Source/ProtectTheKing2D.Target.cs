// Protect the King — 2D. Game target.

using UnrealBuildTool;
using System.Collections.Generic;

public class ProtectTheKing2DTarget : TargetRules
{
	public ProtectTheKing2DTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.V7;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_8;
		ExtraModuleNames.Add("ProtectTheKing2D");
	}
}
