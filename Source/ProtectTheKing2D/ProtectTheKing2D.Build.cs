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

			// AAIController only. No Behavior Trees, no navmesh, no EQS - the
			// enemy needs a controller so CharacterMovement consumes its input,
			// and nothing more than that.
			"AIModule",

			// Enhanced Input: IA_Move (Axis2D), IMC_PTK_Default.
			"EnhancedInput",
			"UMG",
			"SlateCore"
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
		});
	}
}
