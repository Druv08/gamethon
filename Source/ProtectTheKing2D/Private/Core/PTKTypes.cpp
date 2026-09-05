// Protect the King - 2D. Shared gameplay type implementations.

#include "Core/PTKTypes.h"
#include "PaperFlipbook.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKTypes)

//////////////////////////////////////////////////////////////////////////
// FPTKDirectionalFlipbooks

UPaperFlipbook* FPTKDirectionalFlipbooks::GetForDirection(EPTKFacingDirection Direction) const
{
	switch (Direction)
	{
	case EPTKFacingDirection::Down:		return Down;
	case EPTKFacingDirection::Up:		return Up;
	case EPTKFacingDirection::Left:		return Left;
	case EPTKFacingDirection::Right:	return Right;
	default:							return nullptr;
	}
}

bool FPTKDirectionalFlipbooks::IsFullyConfigured() const
{
	return Down != nullptr && Up != nullptr && Left != nullptr && Right != nullptr;
}

int32 FPTKDirectionalFlipbooks::NumConfigured() const
{
	return (Down ? 1 : 0) + (Up ? 1 : 0) + (Left ? 1 : 0) + (Right ? 1 : 0);
}

//////////////////////////////////////////////////////////////////////////
// UPTKTypesLibrary

EPTKFacingDirection UPTKTypesLibrary::DirectionFromInput(
	const FVector2D& Input,
	EPTKFacingDirection CurrentDirection,
	float DeadZone,
	float Hysteresis)
{
	// Below the dead zone we have no opinion - keep whatever we were facing.
	// This is one half of the "last facing direction" guarantee: releasing all
	// movement keys must never snap the character back to a default direction.
	if (Input.SizeSquared() <= FMath::Square(FMath::Max(DeadZone, 0.0f)))
	{
		return CurrentDirection;
	}

	const float AbsX = FMath::Abs(Input.X);
	const float AbsY = FMath::Abs(Input.Y);

	// Hysteresis (0 by default) makes the axis we are *already* using sticky,
	// so analog sticks hovering near a perfect 45 degrees cannot rapidly
	// oscillate between the horizontal and vertical animation sets.
	const float Bias = 1.0f + FMath::Max(Hysteresis, 0.0f);

	const bool bCurrentlyHorizontal =
		(CurrentDirection == EPTKFacingDirection::Left || CurrentDirection == EPTKFacingDirection::Right);

	bool bUseHorizontal;
	if (Hysteresis <= 0.0f)
	{
		// Exact PTK rule, independent of what we were facing:
		//   |X| >  |Y|  -> Left/Right
		//   otherwise   -> Up/Down   (so a perfect 45 degree tie is vertical)
		bUseHorizontal = (AbsX > AbsY);
	}
	else if (bCurrentlyHorizontal)
	{
		// Already horizontal: stay horizontal unless vertical clearly wins.
		bUseHorizontal = !(AbsY > AbsX * Bias);
	}
	else
	{
		// Already vertical: stay vertical unless horizontal clearly wins.
		bUseHorizontal = (AbsX > AbsY * Bias);
	}

	if (bUseHorizontal)
	{
		return (Input.X > 0.0f) ? EPTKFacingDirection::Right : EPTKFacingDirection::Left;
	}

	return (Input.Y > 0.0f) ? EPTKFacingDirection::Up : EPTKFacingDirection::Down;
}

FString UPTKTypesLibrary::DirectionToString(EPTKFacingDirection Direction)
{
	switch (Direction)
	{
	case EPTKFacingDirection::Down:		return TEXT("Down");
	case EPTKFacingDirection::Up:		return TEXT("Up");
	case EPTKFacingDirection::Left:		return TEXT("Left");
	case EPTKFacingDirection::Right:	return TEXT("Right");
	default:							return TEXT("Unknown");
	}
}
