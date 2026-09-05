// Protect the King — 2D. Primary runtime gameplay module.

using UnrealBuildTool;

public class ProtectTheKing2D : ModuleRules
{
	public ProtectTheKing2D(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",

			// 2D character rendering: sprites + flipbooks + APaperCharacter.
			"Paper2D",

			// Enhanced Input: IA_Move (Axis2D), IMC_PTK_Default.
			"EnhancedInput"
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
		});
	}
}
