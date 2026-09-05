// Protect the King - 2D. Player-controlled guard tier.

#include "Characters/PTKGuardCharacter.h"

#include "Components/PTKHealthComponent.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKGuardCharacter)

APTKGuardCharacter::APTKGuardCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// Guards are the characters the player drives, so they own the view.
	bEnableCameraRig = true;

	// Melee only damages the opposing team, which is what will stop a guard's
	// swing from hitting the King he is defending once the King exists.
	Team = EPTKTeam::Guards;

	// GUARD SCALE. A guard is meant to stand against a crowd of enemies, not
	// to trade evenly with one of them, so guard health is roughly two orders
	// of magnitude above a single enemy's. Per-guard Blueprints override this;
	// it is the tier default so a new guard is durable without remembering to
	// set anything.
	if (HealthComponent)
	{
		HealthComponent->SetMaxHealth(7000.0f);
	}

	// RANGE ADVANTAGE. A guard strikes from 3.5 tiles, an enemy from 1.0, so a
	// guard gets 2.5 tiles of reach the enemy has to cross under fire. This is
	// the single most important balance relationship in the prototype, and it
	// is stated in tiles rather than world units so it survives any change to
	// the map scale.
	AttackRangeTiles = 3.5f;

	// A wide arc: the axe is a sweeping weapon and should catch several
	// attackers standing shoulder to shoulder in front of it.
	AttackHitWidthFactor = 0.5f;

	AttackDamage = 25.0f;

	// Facing the camera reads best for a character standing on a spawn pad.
	DefaultFacingDirection = EPTKFacingDirection::Down;
}
