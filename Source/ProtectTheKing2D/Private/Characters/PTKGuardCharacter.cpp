// Protect the King - 2D. Player-controlled guard tier.

#include "Characters/PTKGuardCharacter.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKGuardCharacter)

APTKGuardCharacter::APTKGuardCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// Guards are the characters the player drives, so they own the view.
	bEnableCameraRig = true;

	// Facing the camera reads best for a character standing on a spawn pad.
	DefaultFacingDirection = EPTKFacingDirection::Down;
}
